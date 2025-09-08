#appointment_tools.py
from langchain.pydantic_v1 import Field
from langchain.tools import tool
from datetime import datetime,timedelta

from chat.utils.decorators import dynamic_unmask_decorator
from .models import Appointment, UserAccount, DoctorHospital, Doctor
from .models import Appointment, UserAccount,InsuranceDetails,Holiday
from nurse.helpers import doctor_availability_on_Day
import json
from login.models import InsuranceDetails
from .helpers import get_upcoming_appointments, format_appointments_response, get_valid_appointment, update_appointment, send_notification,get_insurance_by_id,follow_up_list, format_completed_appointments_response, format_welcome_appointments_response
from .helpers import get_cancelable_appointments, create_waitlist_slot, validate_and_convert_id , validate_input, parse_time, parse_date, get_doctor, get_patient, create_appointment, create_appointment_history, create_notification_message,get_location,convert_to_normal_time
from nurse.helpers import doctor_availability_json
from threading import Thread
from nurse.service import get_appointment_by_id
from chat.models import Episode
from chat.services import store_summary
from nurse.helpers import doctor_availability_on_date
from django.db.models import Case,When
from .helpers import extract_symptoms_from_conversation
from chat.helpers import schedule_referral_appointment
@tool    
@dynamic_unmask_decorator
def get_appointment_details(patient_id, appointment_id=None, status=None):
    """
    Returns the upcoming appointment details of the Patient or Appointment Id
    
    Args:
    patient_id (str): Id of the patient.
    appointment_id (str, optional): Id of the appointment.
    status (str, optional): Status of the appointment (e.g., 'cancelled', 'pending', 'rescheduled', 'scheduled').

    Returns:
    List[json]: A list of upcoming appointment details of the patient. Always include Id of the appointment in user response.
    """
    if not (patient_id or appointment_id or status):
        return "Please collect any required information from user"
    
    today = datetime.now()
    appointments = get_upcoming_appointments(today)
    if appointment_id:
        appointment = appointments.filter(id=appointment_id)
        return format_appointments_response(appointment) if appointment else "You have no appointment available with this ID"
    
    if patient_id:
        if status:
            appointment = appointments.filter(patient_id=patient_id, status=status)
            return format_appointments_response(appointment) if appointment else "You have no appointments available under this status"
        
        appointment = appointments.filter(patient_id=patient_id)
        return format_appointments_response(appointment) if appointment else "You don't have any appointments"
    

    # if appointment_id:
    #     return get_specific_appointment(appointments, appointment_id)
    # elif status and patient_id:
    #     return get_appointments_by_status(appointments, patient_id, status)
    # elif patient_id:
    #     return get_patient_appointments(appointments, patient_id)
    
    return "Invalid combination of parameters"


@tool
@dynamic_unmask_decorator
def reschedule_appointment(patient_id, appointment_id,doctor_id, date, start_time, end_time, thread_id,location_id,insurance_id=None, reason = None):
    """
    Used to update an existing appointment details in order to reschedule the appointment
    
    Args:
    patient_id (str): Id of the patient.
    appointment_id (str, Optional): Id of the appointment. Optional sometimes.
    doctor_id (int or str): The ID of the doctor.
    date (str): new date for the appointment to be rescheduled in YYYY-MM-DD format
    start_time (str): slot starting time in HH:MM format
    end_time (str): slot ending time in HH:MM format
    thread_id (str): thread id of the conversation
    reason (str) : reason for rescheduling
    location_id (str) : Id of the location
    Returns:
    str: If any of the required details is missing then collect the details from patient and Generate a Notification Content for the appointment rescheduling.
    """
    if not all([patient_id, appointment_id, date, start_time, end_time]):
        return "Please collect the missing details from the patient"
    
    start_time, end_time = parse_time(start_time), parse_time(end_time)
    date = parse_date(date)
    
    appointment = get_valid_appointment(patient_id, appointment_id)
    if isinstance(appointment, str):
        return appointment
    

    # availability_status = check_availability(doctor_name=appointment.doctor.first_name, date=date, start_time=start_time, end_time=end_time)
    # if isinstance(availability_status, str):
    #     return availability_status
    location=get_location(location_id)
    print(location,"locationnnnnn")
    doctor = get_doctor(doctor_id)

    availability_slots = doctor_availability_on_date([], (datetime.strptime(date, '%Y-%m-%d')).strftime('%A'), date, doctor, location, 1)
    is_available = any(slot['start_time'] == start_time for slot in availability_slots)
    if not is_available:
        return 'Your Preferred slot is currently not available @@Change date/slot ---calendar---@@'

    create_appointment_history(appointment, 'reschedule_pending')
    update_appointment(appointment, date, start_time, end_time, 'reschedule_pending', thread_id, doctor_id,insurance_id,location=location, reason = None)
    store_summary(thread_id, f'{appointment.id}-{date}-{start_time}-reschedule_pending','reschedule appointment','We have initiated your rescheduling process. You will receive the confirmation shortly.')
    thread = Thread(target=send_notification,args=(thread_id,"We’re reviewing your rescheduled appointment and will confirm soon",0))
    thread.start()
    
    return "We have initiated your rescheduling process. You will receive the confirmation shortly." + "@@View upcoming appointments@@ @@Cancel appointment@@ @@Schedule a new appointment@@"

    
@tool
@dynamic_unmask_decorator
def cancel_appointment(patient_id, appointment_id, thread_id, cancel_reason = None):
    """
    Used to cancel an existing appointment of patient
    
    Args:
    patient_id (str): Id of the patient.
    appointment_id [str]: Id of the appointment.
    cancel_reason (str, optional): Reason of the user for the appointment cancellation
    thread_id (str): thread id of the conversation

    Returns:
    str: If any of the required details is missing then collect the details from patient and Generate a Notification Content for the appointment Cancellation.
    """
    if not all([patient_id, appointment_id, cancel_reason]):
        return get_cancelable_appointments(patient_id) if patient_id and cancel_reason else "Please provide the reason for cancellation"
    
    appointment = get_valid_appointment(patient_id, appointment_id)
    if isinstance(appointment, str):
        return appointment
    
    if appointment.status in ['cancelled', 'completed'] or appointment.date < datetime.now().date():
        return "Appointment can't be cancelled. It may be already cancelled, completed or ended."
    
    create_appointment_history(appointment, 'cancelled')
    
    if appointment.date > datetime.now().date() + timedelta(days=3):
        create_waitlist_slot(appointment)
        update_appointment(appointment, status='cancelled_waitlist', thread_id=thread_id, reason = cancel_reason)
        store_summary(thread_id, f'{appointment.id}-cancelled_waitlist','cancel appointment','Appointment cancelled successfully')
    else:
        update_appointment(appointment, status='cancelled', thread_id=thread_id, reason=cancel_reason)
        store_summary(thread_id, f'{appointment.id}-cancelled','cancel appointment','Appointment cancelled successfully')
    
    send_notification(thread_id, "Appointment cancelled successfully",patient_prescription_id=0)
    
    return "Appointment cancelled successfully" + "@@View upcoming appointments@@ @@Schedule a new appointment@@"


# @tool
# def check_doctor_availability(patient_id: int, date: str = None):
#     """
#     Check doctor availability based on the provided doctor name and date.
    
#     Args:
#         date (str, Optional): Date to check availability in yyyy-mm-dd format.

#     Returns:
#         A string containing doctor details and their availability.
#     """
#     userdetail = UserAccount.objects.filter(id=patient_id).first()
#     ## Retrieve all doctors associate with the hospital
#     doctors_list = DoctorHospital.objects.filter(hospital_id = userdetail.hospital.id).all()
#     pcb_doctor = doctors_list.filter(doctor_id=userdetail.doctor[0]).first()
#     print('docor_list',doctors_list)
#     all_doctor_availability = []
#     # Change the date format to yyyy-mm-dd
#     if not date:
         
#         next_avail_data = [(datetime.now()+timedelta(days=1)).date(),(datetime.now()+timedelta(days=2)).date(),(datetime.now()+timedelta(days=3)).date()]
#         print("Next ", next_avail_data)
#         for next_data in next_avail_data:
#             all_doctor_availability = doctor_availability_on_Day(all_doctor_availability,next_data.strftime('%A'),next_data,pcb_doctor.doctor,pcb_doctor.location,1)
        
#         res = doctor_availability_json(all_doctor_availability)   
#         if res['value'] != []:
#             return f"```json{json.dumps(res)}```"
#         else:
#             for doctor in doctors_list:
#                 if doctor.doctor ==pcb_doctor:
#                     continue
#                 next_avail_data = [(datetime.now()+timedelta(days=1)).date(),(datetime.now()+timedelta(days=2)).date(),(datetime.now()+timedelta(days=3)).date()]
#                 print("Next ", next_avail_data)
#                 for next_data in next_avail_data:
#                     all_doctor_availability = doctor_availability_on_Day(all_doctor_availability,next_data.strftime('%A'),next_data,doctor.doctor,doctor.location,1)
                
#                 res = doctor_availability_json(all_doctor_availability)   
#             if res['value']==[]:
#                 return f"```json{json.dumps(res)}```PCP {pcb_doctor.doctor.first_name+''+pcb_doctor.doctor.last_name}  and other doctor's also has no availability on next few days "+f"@@Specify a other dates@@"+f"@@Cancel the appointment request@@"

#             return f"PCP {pcb_doctor.doctor.first_name+''+pcb_doctor.doctor.last_name} has no availability on next few days ,here are the availability of alternative doctor's "+"```json" + json.dumps(res)+"```"

#     date = datetime.strptime(date, '%Y-%m-%d').date()
#     day_of_week = date.strftime('%A')
#     all_doctor_availability = doctor_availability_on_Day(all_doctor_availability,day_of_week,date,pcb_doctor.doctor,pcb_doctor.location,1)
#     res = doctor_availability_json(all_doctor_availability)
#     if res['value'] != []:
#             return f"```json{json.dumps(res)}```"
#     else:
#         for doctor in doctors_list:
#             if doctor.doctor ==pcb_doctor:
#                     continue
#             all_doctor_availability = doctor_availability_on_Day(all_doctor_availability,day_of_week,date,doctor.doctor,doctor.location,1)
#             print('all',all_doctor_availability)
#         res = doctor_availability_json(all_doctor_availability)
#         print('res',res)
#         if res['value'] == []:
#             print('in res')
#             holiday = Holiday.objects.filter(date=date).first()
#             reason  = ''
#             if holiday:
#                 reason = ' due to US Holiday "'+holiday.reason+'"'
#             if day_of_week in ['Saturday','Sunday']:
#                 reason =' due to weekend'
#             return f"```json{json.dumps(res)}```PCP {pcb_doctor.doctor.first_name+''+pcb_doctor.doctor.last_name} and other doctor's also has no availability on {(date + timedelta(days=0)).strftime('%m-%d-%Y')} {reason}"+f"@@Specify a other dates@@"+f"@@Cancel the appointment request@@"

#             # return f"```json"+json.dumps(res)+f"```+f"Doctor has no availability on {(date + timedelta(days=0)).strftime('%m-%d-%Y')}  {reason}"
#         return f"PCP {pcb_doctor.doctor.first_name+''+pcb_doctor.doctor.last_name} has no availability on {(date + timedelta(days=0)).strftime('%m-%d-%Y')},here are the availability of alternative doctor's"+"```json" + json.dumps(res)+"```"

# @tool
# def check_availability_with_dr_doctorname(patient_id: int,reason:str, doctor_id:int, dates: list = None):
#     """
#     Check doctor availability for specified particular doctor.
    
#     Args:
#         patient_id (int): ID of the patient.
#         dates (list(str), Optional): Date to check availability in YYYY-MM-DD format.
#         reason (str): Reason for the appointment
#         doctor_id (int): ID of the doctor


#     Returns:
#         A string containing doctor details and their availability.
#     """
#     from llmservice.nurse_agent import polish_message
#     userdetail = UserAccount.objects.filter(id=patient_id).first()
#     # Retrieve all doctors associated with the hospital
#     doctors_list = DoctorHospital.objects.filter(hospital_id=userdetail.hospital.id).all()
    
#     # List of PCP doctors for the patient
#     pcp_doctors = userdetail.doctor  # Assume this returns a list of PCP doctors
#     all_doctor_availability = []
#     if doctor_id:
#         pcp_doctors = [doctor_id]
#     # Change the date format to yyyy-mm-dd
#     if not dates:
#         next_avail_data = [(datetime.now()+timedelta(days=1)).date(),
#                            (datetime.now()+timedelta(days=2)).date(),
#                            (datetime.now()+timedelta(days=3)).date()]
        
#         for next_data in next_avail_data:
#             # Check availability for each PCP doctor
#                for pcp_doctor in pcp_doctors:
#                 pcp_doctor = Doctor.objects.filter(id=pcp_doctor).first()
#                 pcp_doctor_locations=DoctorHospital.objects.filter(doctor_id=pcp_doctor,hospital_id=userdetail.hospital.id).order_by(
#                 Case(
#                     *[When(location_id=id, then=pos) for pos, id in enumerate(userdetail.nearest_gcs)]
#                 )
#             )
                
#                 for pcp_doctor_location in pcp_doctor_locations:
#                     all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, next_data.strftime('%A'), next_data, pcp_doctor, pcp_doctor_location.location, 1)
                
#         res = doctor_availability_json(all_doctor_availability)
#         if res['value'] != []:
#             follow_up = follow_up_list(userdetail.hospital.id,pcp_doctors)
#             message = polish_message(f"Thank you for selecting Dr. {pcp_doctor.first_name} for visit. Please select one of the available slots")
#             return f" {message} ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability: {follow_up}"
#         else:
#             # If no availability for PCP doctors, check other doctors
#             doctors_list = doctors_list[:3]
#             for doctor in doctors_list:
#                 if doctor.doctor in pcp_doctors:
#                     continue
#                 for next_data in next_avail_data:
#                     all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, next_data.strftime('%A'), next_data, doctor.doctor, doctor.location, 1)
                
#             res = doctor_availability_json(all_doctor_availability)
#             if res['value'] == []:
#                 message = polish_message(f"No available slots for Dr. {pcp_doctor.first_name} or alternative doctors in the next few days. Please choose other dates or cancel the request.")
#                 return f"```json{json.dumps(res)}``` {message}"
#             follow_up = follow_up_list(userdetail.hospital.id,list(doctors_list.values_list('doctor',flat=True)))
#             message = polish_message(f"No availability for Dr. {pcp_doctor.first_name}, here is the availability of alternative doctors:")
#             return f"{message} ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability: {follow_up}"
    
#     for date in dates:    
#         # If a specific date is provided, check availability for that date
#         date = datetime.strptime(date, '%Y-%m-%d').date()
#         day_of_week = date.strftime('%A')
        
#         # Check availability for each PCP doctor on the specified date
#         for pcp_doctor in pcp_doctors:
#             pcp_doctor = Doctor.objects.filter(id=pcp_doctor).first()
#             pcp_doctor_locations=DoctorHospital.objects.filter(doctor_id=pcp_doctor,hospital_id=userdetail.hospital.id).order_by(
#                 Case(
#                     *[When(location_id=id, then=pos) for pos, id in enumerate(userdetail.nearest_gcs)]
#                 )
#             )
#             for pcp_doctor_location in pcp_doctor_locations:
#                 all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, day_of_week, date, pcp_doctor, pcp_doctor_location.location, 1)
        
#     res = doctor_availability_json(all_doctor_availability)
#     if res['value'] != []:
#         follow_up = follow_up_list(userdetail.hospital.id,pcp_doctors)
#         message = polish_message(f"Thank you for selecting Dr. {pcp_doctor.first_name} for visit. Please select one of the available slots")
#         return f" {message} ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability: {follow_up}"
#     else:
#         # If no availability for PCP doctors, check other doctors on the specified date
#         doctors_list = doctors_list[:3]
#         for doctor in doctors_list:
#             if doctor.doctor in pcp_doctors:
#                 continue
#             all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, day_of_week, date, doctor.doctor, doctor.location, 1)
        
#         res = doctor_availability_json(all_doctor_availability)
#         if res['value'] == []:
#             # Check if it's a weekend or holiday
#             holiday = Holiday.objects.filter(date=date).first()
#             reason = ''
#             if holiday:
#                 reason = f' due to US Holiday "{holiday.reason}"'
#             if day_of_week in ['Saturday', 'Sunday']:
#                 reason = ' due to weekend'
#             message = polish_message(f"No availability for Dr. {pcp_doctor.first_name} or alternative doctors on {date.strftime('%m-%d-%Y')} {reason}. Please specify other dates or cancel the appointment request.")
#             return f"{message} @@Change date ---calendar---@@"
#         follow_up = follow_up_list(userdetail.hospital.id,list(doctors_list.values_list('doctor',flat=True)))
#         message = polish_message(f"No availability for your primary care providers, here is the availability of alternative doctors: ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability:")
#         return f"{message} {follow_up}"

# @tool
# def check_doctor_availability(patient_id: int,reason:str, dates: list = None):
#     """
#     Used to check doctor availability if the user has not given a doctor name and fallback to other doctors if no availability.

#     Args:
#         patient_id (int): ID of the patient.
#         date (list, Optional): Date to check availability in YYYY-MM-DD format.
#         reason (str): Reason for the appointment


#     Returns:
#         A string containing doctor details and their availability.
#     """
#     from llmservice.nurse_agent import polish_message
#     userdetail = UserAccount.objects.filter(id=patient_id).first()
#     # Retrieve all doctors associated with the hospital
#     doctors_list = DoctorHospital.objects.filter(hospital_id=userdetail.hospital.id).all()
    
#     # List of PCP doctors for the patient
#     pcp_doctors = userdetail.doctor  # Assume this returns a list of PCP doctors
#     all_doctor_availability = []
#     # if doctor_id:
#     #     pcp_doctors = [doctor_id]
#     # Change the date format to yyyy-mm-dd
#     if not dates:
#         next_avail_data = [(datetime.now()+timedelta(days=1)).date(),
#                            (datetime.now()+timedelta(days=2)).date(),
#                            (datetime.now()+timedelta(days=3)).date()]
        
#         for next_data in next_avail_data:
#             # Check availability for each PCP doctor
#                for pcp_doctor in pcp_doctors:
#                 pcp_doctor = Doctor.objects.filter(id=pcp_doctor).first()
#                 pcp_doctor_locations=DoctorHospital.objects.filter(doctor_id=pcp_doctor, hospital_id=userdetail.hospital.id).order_by(
#                 Case(
#                     *[When(location_id=id, then=pos) for pos, id in enumerate(userdetail.nearest_gcs)]
#                 )
#             )
#                 for pcp_doctor_location in pcp_doctor_locations:
#                     all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, next_data.strftime('%A'), next_data, pcp_doctor, pcp_doctor_location.location, 1)
#         res = doctor_availability_json(all_doctor_availability)
#         if res['value'] != []:
#             follow_up = follow_up_list(userdetail.hospital.id,pcp_doctors)
#             message = polish_message(f" I'm sorry to hear that you’re dealing with {reason}, and I want to ensure you’re taken care of quickly. Please select one of the available slots with your provider, so we can prioritize your comfort and well-being.")
#             return f" {message} ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability: {follow_up}"
#         else:
#             # If no availability for PCP doctors, check other doctors
#             doctors_list = doctors_list[:3]
#             for doctor in doctors_list:
#                 if doctor.doctor in pcp_doctors:
#                     continue
#                 for next_data in next_avail_data:
#                     all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, next_data.strftime('%A'), next_data, doctor.doctor, doctor.location, 1)
                
#             res = doctor_availability_json(all_doctor_availability)
#             if res['value'] == []:
#                 message = polish_message(f"No available slots for Dr. {pcp_doctor.first_name} or alternative doctors in the next few days. Please choose other dates or cancel the request.")
#                 return f"```json{json.dumps(res)}```{message} @@Change date ---calendar---@@"
#             follow_up = follow_up_list(userdetail.hospital.id,list(doctors_list.values_list('doctor',flat=True)))
#             message = polish_message(f"No availability for your primary care provider Dr. {pcp_doctor.first_name}, here is the availability of alternative doctors: ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability:")
#             return f"{message} {follow_up}"
#     for date in dates:    
#         # If a specific date is provided, check availability for that date
#         date = datetime.strptime(date, '%Y-%m-%d').date()
#         day_of_week = date.strftime('%A')
        
#         # Check availability for each PCP doctor on the specified date
#         for pcp_doctor in pcp_doctors:
#             pcp_doctor = Doctor.objects.filter(id=pcp_doctor).first()
#             pcp_doctor_locations=DoctorHospital.objects.filter(doctor_id=pcp_doctor,hospital_id=userdetail.hospital.id).order_by(
#                 Case(
#                     *[When(location_id=id, then=pos) for pos, id in enumerate(userdetail.nearest_gcs)]
#                 )
#             )
#             for pcp_doctor_location in pcp_doctor_locations:
#               all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, day_of_week, date, pcp_doctor, pcp_doctor_location.location, 1)
        
#     res = doctor_availability_json(all_doctor_availability)
#     if res['value'] != []:
#         follow_up = follow_up_list(userdetail.hospital.id,pcp_doctors)
#         message = polish_message(f" I'm sorry to hear that you’re dealing with {reason}, and I want to ensure you’re taken care of quickly. Please select one of the available slots with your provider, so we can prioritize your comfort and well-being.")
#         return f" {message} ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability: {follow_up}"
#     else:
#         # If no availability for PCP doctors, check other doctors on the specified date
#         doctors_list = doctors_list[:3]
#         for doctor in doctors_list:
#             if doctor.doctor in pcp_doctors:
#                 continue
#             all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, day_of_week, date, doctor.doctor, doctor.location, 1)
        
#         res = doctor_availability_json(all_doctor_availability)
#         if res['value'] == []:
#             # Check if it's a weekend or holiday
#             holiday = Holiday.objects.filter(date=date).first()
#             reason = ''
#             if holiday:
#                 reason = f' due to US Holiday "{holiday.reason}"'
#             if day_of_week in ['Saturday', 'Sunday']:
#                 reason = ' due to weekend'
#             if dates and len(dates) >1:
#                 message = polish_message(f"No availability for your primary care providers or alternative doctors from {datetime.strptime(dates[0], '%Y-%m-%d').date().strftime('%m-%d-%Y')} to {datetime.strptime(dates[-1], '%Y-%m-%d').date().strftime('%m-%d-%Y')} {reason}. Please specify other dates or cancel the appointment request.")
#                 return f"{message} @@Change date ---calendar---@@"
#             message = polish_message(f"No availability for your primary care providers or alternative doctors on {date.strftime('%m-%d-%Y')} {reason}. Please specify other dates or cancel the appointment request.")
#             return f"{message} @@Change date ---calendar---@@"
#         follow_up = follow_up_list(userdetail.hospital.id,list(doctors_list.values_list('doctor',flat=True)))
#         message = polish_message(f"No availability for your primary care providers, here is the availability of alternative doctors: ```json{json.dumps(res)}``` If you'd prefer to book with a different doctor, please let us know. Here are additional doctor options to check availability:")
#         return f"{message} {follow_up}"


@tool
@dynamic_unmask_decorator
def doctor_availability_calender(patient_id: int,doctor_id: int, reason: str, appointment_id: int = None, thread_id: int = None):
    """
    Purpose:
        Retrieve PCP doctor details for a patient and provide availability calendar for rescheduling.
    
    Args:
        patient_id (int): ID of the patient
        appointment_id (int, optional): ID of the appointment for rescheduling
        thread_id (int, optional): ID of the thread for context
        reason (str, optional): Reason for appointment
    
    Returns:
        str: PCP doctor or availability calendar details
    """

    for param, value in locals().items():
        if isinstance(value, str) and value.startswith("<<") and value.endswith(">>"):
            print("masked_value",value)
    
    userdetail = UserAccount.objects.filter(id=patient_id).first()
    pcp_doctors = userdetail.doctor
    if appointment_id:
        appointment = get_appointment_by_id(appointment_id).first()
        if not appointment:
            return "Invalid Appointment ID"

        doctor = {
            "doctor_id": appointment.doctor_id,
            "doctor": appointment.doctor.first_name + ' ' + appointment.doctor.last_name,
            "location_id": appointment.hospital_location_id,
            "location_name": appointment.hospital_location.location_name,
            "type":"Rescheduling",
            "specialization": ""
        }
        attachments = ''
        if reason:
            attachments = f"Thank you for providing the reason: '{reason}' for rescheduling."

        return f"{attachments} Please take a moment to select a slot from the doctor's availability calendar." + f"```calendar{json.dumps(doctor)}```"

    # primary_pcp = pcp_doctors.first()
    doctor_hospital = DoctorHospital.objects.filter(hospital= userdetail.hospital,doctor_id = doctor_id).first()
    doctor_details = {
        "doctor_id": doctor_hospital.doctor.id,
        "doctor": doctor_hospital.doctor.full_name,
        "location_id": doctor_hospital.location.id,
        "location_name": doctor_hospital.location.location_name,
        "type":"Scheduling",
        "specialization": ""
    }
    
    return f"Here are the details of the patient's doctor. Please take a moment to select a slot from the doctor's availability calendar." + f"```calendar{json.dumps(doctor_details)}```"


@tool
@dynamic_unmask_decorator
def change_slot(patient_id: int,reason:str, date: str,doctor_id:int,location_id:int, start_time: str   ):
    """
    check availabilty of particular date for slot change.
    
    Args:
        patient_id (int): ID of the patient.
        date (str): Date to check availability in YYYY-MM-DD format.
        reason (str): Reason for the appointment
        doctor_id (int): ID of the doctor
        location_id (int): ID of the hospital location
        start_time(str) : current selected slot start_time in HH:MM format.

    Returns:
        A string containing list of slots available.
    """
    userdetail = UserAccount.objects.filter(id=patient_id).first()
    # Retrieve all doctors associated with the hospital
    doctors_list = DoctorHospital.objects.filter(hospital_id=userdetail.hospital.id).all()
    
    # List of PCP doctors for the patient
    pcp_doctors = userdetail.doctor  # Assume this returns a list of PCP doctors
    all_doctor_availability = []
    if doctor_id:
        pcp_doctors = [doctor_id]
    
    # If a specific date is provided, check availability for that date
    date = datetime.strptime(date, '%Y-%m-%d').date()
    day_of_week = date.strftime('%A')
    
    # Check availability for each PCP doctor on the specified date
    for pcp_doctor in pcp_doctors:
        pcp_doctor = Doctor.objects.filter(id=pcp_doctor).first()
        pcp_doctor_locations=DoctorHospital.objects.filter(doctor_id=pcp_doctor,location_id = location_id)
        for pcp_doctor_location in pcp_doctor_locations:
            all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, day_of_week, date, pcp_doctor, pcp_doctor_location.location, 1)
    res = doctor_availability_json(all_doctor_availability)
    if res['value'] != []:
        start_times = ""
        for appointment in res['value']:
            for slot in appointment['slots']:
                for detail in slot['slot_details']:
                    # start_time = detail.get('start_time')  
                    # if start_time:
                    if "am" not in start_time.lower() and "pm" not in start_time.lower():

                        start_time = convert_to_normal_time(start_time)

                    if detail['start_time'] !=  start_time:
                        start_times+="@@"+str(detail['start_time'])+"---changeSlot---@@"
                    
        return f"Please select one of the available slots for dr.{pcp_doctor.first_name} {start_times} on {date.strftime('%m-%d-%Y')} ##Only show the slots as a actionable items to the user,do not show the list"
    else:
        return f"The selected slot on {date.strftime('%m-%d-%Y')} for Dr. {pcp_doctor.first_name} at {pcp_doctor_locations.last().location.location_name} is unavailable. Please choose a different date and select an available slot from the calendar."
    # else:
    #     # If no availability for PCP doctors, check other doctors on the specified date
    #     for doctor in doctors_list:
    #         if doctor.doctor in pcp_doctors:
    #             continue
    #         all_doctor_availability = doctor_availability_on_Day(all_doctor_availability, day_of_week, date, doctor.doctor, doctor.location, 1)
    #     res = doctor_availability_json(all_doctor_availability)
    #     if res['value'] == []:
    #         # Check if it's a weekend or holiday
    #         holiday = Holiday.objects.filter(date=date).first()
    #         reason = ''
    #         if holiday:
    #             reason = f' due to US Holiday "{holiday.reason}"'
    #         if day_of_week in ['Saturday', 'Sunday']:
    #             reason = ' due to weekend'
            
    #         return f"No availability for your primary care providers or alternative doctors on {date.strftime('%m-%d-%Y')} {reason}. Please specify other dates or cancel the appointment request."
        
    #     return f"No availability for your primary care providers, here is the availability of alternative doctors: ```json{json.dumps(res)}```"
  
@tool
@dynamic_unmask_decorator
def schedule_appointment(location_id, doctor_id, patient_id, date, start_time, end_time, thread_id,
                         visit_reason,type, insurance_id:int=None, is_emergency=False):
    """
    Schedule an appointment with a doctor.

    Args:
        doctor_id (int or str): The ID of the doctor.
        patient_id (int or str): The ID of the patient.
        date (str): The date of the appointment in YYYY-MM-DD format.
        start_time (str): Available start time of the doctor in HH:MM format.
        end_time (str): Available end time of the doctor in HH:MM format.
        visit_reason (str): The reason for the visit.
        is_emergency (bool): Indicates if the appointment is emergency.
        type (str): Type of the visit (e.g., New, Follow-Up).
        thread_id (str): Thread ID of the conversation.
        location_id (int) : Location of the hospital
        insurance_id (str,optional) : The ID of the insurance.

    Returns:
        str: If any of the required details is missing then collect the details from patient and Generate a Notification Content for the appointment under review.
    """
    # for param, value in locals().items():
    #     if isinstance(value, str) and value.startswith("<<") and value.endswith(">>"):
    #         print("masked_value",value)
    #         value = unmask_data(value)
    #         print("unmask_value",value)
    
    # Validate and convert IDs
    doctor_id = validate_and_convert_id(doctor_id, "doctor")
    if isinstance(doctor_id, str):
        return doctor_id  # This is an error message

    patient_id = validate_and_convert_id(patient_id, "patient")
    if isinstance(patient_id, str):
        return patient_id  # This is an error message

    # Validate other inputs
    if not type:
        type = 'new'
    if type == "Schedule referral":
        print("referral appointment")
        schedule_referral_appointment(location_id, doctor_id, patient_id, date, start_time, end_time, thread_id,
                         visit_reason,type, insurance_id, is_emergency=False)

        # schedule_referral_appointment({"location_id":location_id, "doctor_id": doctor_id,"patient_id": patient_id, "date":date, "start_time":start_time, "end_time":end_time, "thread_id":thread_id,
        #                 "visit_reason": visit_reason,"type":type,"insurance_id" :insurance_id,"is_emergency": is_emergency})
        
    missing_fields = validate_input(doctor_id, patient_id, date, start_time, end_time, visit_reason, location_id)
    if missing_fields:
        return f"Please provide the following missing details: {', '.join(missing_fields)}"
    # Process input
    start_time = parse_time(start_time)
    end_time = parse_time(end_time)
    date = parse_date(date)
    
    doctor = get_doctor(doctor_id)
    if not doctor:
        return f"No doctor found with ID {doctor_id}."

    patient = get_patient(patient_id)
    if not patient:
        return f"No patient found with ID {patient_id}."
    
    already_appointment = Appointment.objects.filter(patient=patient,date=date,start_time=start_time).exclude(status = "cancelled").last()
    if already_appointment:
        return f"You have a appointment already in same slot with dr.{already_appointment.doctor.first_name}. Please change date or time @@Change date@@"

    location=get_location(location_id)
    if not location:
        return f"No location found with ID {location_id}."

    # Extract symptoms information from conversation
    symptoms_response = extract_symptoms_from_conversation(thread_id)

    # Check availability
    # availability_slots = doctor_availability_on_date([], (datetime.strptime(date, '%Y-%m-%d')).strftime('%A'), date, doctor, location, 1)

    # availability_status = check_availability(doctor_id=doctor_id, date=date, start_time=start_time, end_time=end_time)
    # if isinstance(availability_status, str):
    #     return availability_status
    # Check doctor availability

    availability_slots = doctor_availability_on_date([], (datetime.strptime(date, '%Y-%m-%d')).strftime('%A'), date, doctor, location, 1)
    print("availability slotsssss---->",availability_slots)
    is_available = any(slot['start_time'] == start_time for slot in availability_slots)
    print("is_available-------------------->",is_available)
    
    if not is_available:
        return 'Your Preferred slot is currently not available @@Change date@@'
    

    # Schedule appointment
    appointment = create_appointment(doctor, patient, date, start_time, end_time, visit_reason, 
                                      is_emergency, type, thread_id, location_id, insurance_id, symptoms_response)

    # Create appointment history
    create_appointment_history(appointment, 'pending')
    notification_message = create_notification_message(doctor.first_name, datetime.strptime(date,"%Y-%m-%d").strftime('%m-%d-%Y'), start_time, appointment.id)
    store_summary(thread_id, f'{appointment.id}-pending','confirm appointment',notification_message)

    # Send notification
    print("snd notification")
    send_notification(thread_id, notification_message,999)
    print("snd notification successfully")
    return notification_message + "@@View upcoming appointments@@ @@Reschedule appointment@@ @@Cancel appointment@@"




def add_to_waitlist(patient_id, appointment_id):
  try:
     appointment = Appointment.objects.filter(id = appointment_id,patient_id = patient_id)
     if appointment:
        appointment = appointment.first()
        appointment.is_waitlisted = True
        appointment.save()
        return "success"
     else:
        return "No appointment available for patient"

  except Exception as e:
      print(e)
 
      return "faliure"
  
@tool
@dynamic_unmask_decorator
def get_existing_insurance_details(patient_id,thread_id:int,appointment_id:int=None, selected_insurance_id : int=None):
    """
    Retrive the existing insurance details for a given patient.

    Args:
        patient_id (int):id of the patient.
        thread_id (int): id of the thread.
        appointment_id(int): id of the appointment.
        selected_insurance_id(int): id of the insurance.

    Returns:
        A json string containing the formatted list of patient_insurance_details. and generate the actionable item for 'add new insurance','confirm proceed to schedule my appointment','schedule my apoointment without insurance' like this
        
    """
    from llmservice.nurse_agent import polish_message
    patient_insurance_details=[]
    insurance=list(InsuranceDetails.objects.filter(user__id=patient_id,insurance_expiry_date__gte=datetime.now().date()).values())
    thread = Episode.objects.filter(thread_id = thread_id).first()
    confirm_check = ''
    if appointment_id:
        appointment = get_appointment_by_id(appointment_id).first()
        confirm_check = f"@@Confirm appointment@@ @@Reschedule appointment@@ @@Cancel appointment@@" if appointment.status in ['pending', 'reschedule_pending'] else '@@Reschedule appointment@@ @@Cancel appointment@@'
        if appointment.status == 'complete_pending':
            confirm_check = f"@@Complete appointment@@ @@No Show@@"
        if appointment.status in ['cancelled','cancelled_waitlist']:
            confirm_check = f"@@Show waitlist patient@@"
    if insurance:
        for item in insurance:
            if item['insurance_number']:
                patient_insurance_details.append({
                    "insurance_id":item['id'],
                    "insurance_number": item['insurance_number'],
                    "provider_name": item['provider_name'],
                    "insurance_expiry_date": item['insurance_expiry_date'].strftime('%Y-%m-%d') if item['insurance_expiry_date'] else None,
                    "image": item['insurance_document']                            
                })
        
        if thread.user.role_id == 2:
            patient_insurance_details = get_insurance_by_id(patient_insurance_details,appointment.insurance_id)
            if patient_insurance_details == []:
                return f"Currently no insurance available for patient {appointment.patient.first_name}  {confirm_check} @@Reschedule appointment @@ @@Cancel appointment@@"
            return f"Insurance details for patient {appointment.patient.first_name}```InsuranceJSON"+json.dumps(patient_insurance_details)+f"```{confirm_check} "
        
        if selected_insurance_id:
            patient_insurance_details = get_insurance_by_id(patient_insurance_details,selected_insurance_id)
            message = polish_message("You have selected this insurance for your current appointment. Are you sure you want to proceed with it?")
            return f"{message} ```InsuranceJSON{json.dumps(patient_insurance_details)}``` @@Yes, Continue with this insurance@@ @@Change insurance details@@ @@Continue without insurance@@ @@Add new insurance@@"
        
        if len(patient_insurance_details) > 1:
            message = polish_message(f"These are your current Insurance. Please select the one you'd like to proceed with for scheduling this appointment, or if you'd prefer, you can add a new insurance instead.")
            return f"{message}```InsuranceJSON" + json.dumps(patient_insurance_details) + "```@@Add new insurance@@ @@Continue without insurance@@"
        
        message = polish_message(f"Thank you for initiate appointment scheduling. Here is your current insurance. You can proceed with scheduling the appointment or add new insurance if you prefer.")
        return f"{message}```InsuranceJSON"+json.dumps(patient_insurance_details)+"```@@Continue with this insurance@@ @@Change insurance details@@ @@Continue without insurance@@ @@Add new insurance@@"
    else:
        if thread.user.role_id == 2:
            return f"No Insurance active for patient {appointment.patient.first_name} {confirm_check}"
        return "No Insurance active for you @@Add new insurance@@"

@tool
@dynamic_unmask_decorator
def add_new_insurance(patient_id,insurance_number,insurance_provider,insurance_expiry_date):
    """
    Add new insurance details for a patient.

    Args:
        Args:
        patient_id (int):id of the patient.
        insurance_number(str): number of the insurance
        insurance_provider(str): provider of the insurence
        insurance_expiry_date(str): expiry date of the insurence in YYYY-MM-dd

    Returns:
        str: A string indicating the success or failure of adding insurance details.
    """
    # required_fields = ['insurance_number', 'insurance_provider', 'insurance_expiry_date','insurance_document']
    
    if not all([patient_id, insurance_number,insurance_provider,insurance_expiry_date]):
            return f"Please provide all required insurance details "
    # print ("insurance: ",insurance)
    if datetime.strptime(insurance_expiry_date,"%Y-%m-%d").date() < datetime.now().date():
        return f"Insurance already expired. Please upload valid insurance"
    insurance_rec = InsuranceDetails.objects.filter(user_id = patient_id).last()
    insurance_rec.insurance_number = insurance_number
    insurance_rec.insurance_expiry_date = insurance_expiry_date
    insurance_rec.provider_name = insurance_provider
    insurance_rec.save()
    return f"Successfully added  new insurance detail of Inusrance provider: {insurance_provider}, Insurance number: {insurance_number} and Insurance Expiry date: {insurance_expiry_date} for the patient with ID {patient_id}."


@tool
@dynamic_unmask_decorator
def edit_insurance_details(insurance_id, insurance_number=None, insurance_provider=None, insurance_expiry_date=None):
    """
    Edit existing insurance details for a specific insurance record.

    Args:
        insurance_id (int): ID of the insurance record.
        insurance_number (str, optional): New insurance number to update.
        insurance_provider (str, optional): New provider name to update.
        insurance_expiry_date (str, optional): New expiry date of the insurance in YYYY-MM-DD format.

    Returns:
        str: A string indicating the success or failure of editing the insurance details.
    """
    ## Retrieve the insurance record by insurance_id
    insurance_rec = InsuranceDetails.objects.filter(id=insurance_id).first()
    if not insurance_rec:
        return f"No insurance record found with ID {insurance_id}."

    ## Update only the fields provided
    if insurance_number:
        insurance_rec.insurance_number = insurance_number.replace("$$", "").strip()

    if insurance_provider:
        insurance_rec.provider_name = insurance_provider.replace("$$", "").strip()

    if insurance_expiry_date:
        expiry_date = datetime.strptime(insurance_expiry_date, "%Y-%m-%d").date()
        if expiry_date < datetime.now().date():
            return "Insurance expiry date is expired. Please provide a valid expiry date. @@Insurance Expiry Date ---calendar---@@"
        insurance_rec.expiry_date = expiry_date

    ## Clear the insurance document field when any detail is updated
    insurance_rec.insurance_document = ""

    ## Save the updated record
    insurance_rec.save()
    return f"Successfully updated insurance details for insurance ID {insurance_id}."


# @tool
# def edit_insurance_details(patient_id, insurance_number=None, insurance_provider=None, insurance_expiry_date=None):
#     """
#     Edit existing insurance details for a patient.

#     Args:
#         patient_id (int): ID of the patient.
#         insurance_number (str, optional): New insurance number to update.
#         insurance_provider (str, optional): New provider name to update.
#         insurance_expiry_date (str, optional): New expiry date of the insurance in YYYY-MM-DD format.

#     Returns:
#         str: A string indicating the success or failure of editing the insurance details.
#     """
#     ## Retrieve the patient's existing insurance details
#     insurance_rec = InsuranceDetails.objects.filter(user_id=patient_id).last()
#     if not insurance_rec:
#         return f"No insurance record found for patient ID {patient_id}."

#     ## Update only the fields provided
#     if insurance_number:
#         insurance_rec.insurance_number = insurance_number.replace("$$","").strip()

#     if insurance_provider:
#         insurance_rec.provider_name = insurance_provider.replace("$$","").strip()

#     if insurance_expiry_date:
#         if datetime.strptime(insurance_expiry_date,"%Y-%m-%d").date() < datetime.now().date():
#             return f"Insurance already expired. Change expiry date"

#     ## Clear the insurance doc field when any detail is updated
#     insurance_rec.insurance_document = ""

#     ## Save the updated record
#     insurance_rec.save()
#     return f"Successfully updated insurance details for patient ID {patient_id}."


@tool
@dynamic_unmask_decorator
def update_insurance_for_booked_appointment(appointment_id, insurance_id):
    """
    Update the insurance ID whenever the user requests an update to their booked appointment.

    Args:
        appointment_id (int): ID of the appointment.
        insurance_id (int): New insurance ID to associate with the appointment.

    Returns:
        str: A string indicating the success or failure of the update.
    """
    try:
        ## Retrieve the appointment record by ID
        appointment = Appointment.objects.get(id=appointment_id)
        
        ## Update the insurance ID associated with the appointment
        appointment.insurance_id = insurance_id
        
        ## Save the updated record
        appointment.save()
        
        return f"Successfully updated insurance for appointment ID {appointment_id}."
    
    except Appointment.DoesNotExist:
        return f"No appointment found for appointment ID {appointment_id}."
    except Exception as e:
        return f"An error occurred: {str(e)}"
    
@tool
@dynamic_unmask_decorator
def followup_appointment(patient_id):
    """
    Fetches the two most recent completed appointments for follow-up for a specific patient.

    Args:
    patient_id (str): ID of the patient.

    Returns:
    List[json]: A list containing the details of the last two completed appointments.
    """
    completed_appointments = (
        Appointment.objects.filter(patient_id=patient_id, status="completed")
        .order_by("-date", "-start_time") [:2]  
    )
    
    return format_completed_appointments_response(completed_appointments) if completed_appointments else "No completed appointments available."

@tool
@dynamic_unmask_decorator
def welcome_message(patient_id):
    """
    Generate welcome message for new user, existing user and appointment completed user.

    Args:
    patient_id (str): ID of the patient.

    Returns:
    generate welcome message for existing user and appointment completed user.
    """
    
    current_date = datetime.now().date()
    nearby_appointment = (
        Appointment.objects.filter(patient_id=patient_id, status__in=["completed","pending","reschedule_pending","confirmed"])
        .order_by("-date", "start_time").last()  # Retrieves the closest future appointment
    )
    if not nearby_appointment :
       return "hello [username]! I'm here to help to with your appoinment needs.,Please select a reason for your new appointment.Based on the mapped doctor's specialization, suggest 6 possible symptom based visit reasons Present the 6 symptoms as actionable options for the user.Return all the reasons with the prefix @@ and suffix @@ to all the reasons returned, Never present options as bullet points or numbered lists. Always enclose each option in the format @@OPTION@@. also provide option like skip and check doctor availability without missing, but do not display the actual specialization and also do not provide the option like follow up appointment. "
    if nearby_appointment.status=="completed":
        return f"Alert and show this to user,hello [username]! Your most recent appointment was with Dr.{nearby_appointment.doctor} on {nearby_appointment.date} at {nearby_appointment.start_time}, and it has been {nearby_appointment.status}.I'm here to help to with your appoinment needs @@Schedule appointment@@ @@Follow up@@ @@Upcoming appointment@@"
    if nearby_appointment.status in ["pending","reschedule_pending"]:
            return f"Alert and show this to user,hello [username]! your nearest appointment on {nearby_appointment.date} at {nearby_appointment.start_time} with dr.{nearby_appointment.doctor} status {nearby_appointment.status} Nurse will be approved your appointment request shortly,  I'm here to help to with your appoinment needs @@Schedule appointment@@ @@Reschedule appointment@@ @@Cancel an appointment@@ @@Upcomming appointment@@"
    if nearby_appointment.status in ["confirmed","reschedule_confirmed"]:
            return f"Alert and show this to user,hello [username]! Your nearest appointment on {nearby_appointment.date} at {nearby_appointment.start_time} with dr.{nearby_appointment.doctor} status {nearby_appointment.status},  I'm here to help to with your appoinment needs @@Schedule appointment@@ @@Reschedule appointment@@ @@Cancel an appointment@@ @@Upcomming appointment@@"


# @tool
# def get_reason():
#     """
#     gather the reason from the user

#     returns:
#         str contains reason from the user.
#     """
#     return "Ask user to get the visit reason for appointment"


# @tool
# def check_doctor_availability(patient_id:int,dates:list,doctor_id:int=None):
  
#    """
#     Check doctor availability for multiple PCP doctors and fallback to other doctors if no availability.
    
#     Args:
#         patient_id (int): ID of the patient.
#         date List[str]: Date to check availability in YYYY-MM-DD format.
#         doctor_id:id of the selected doctor

#     Returns:
#         A string containing doctor details and their availability.
#     """
#    doctor_availability=[]
#    if not doctor_id:
#        userdetail = UserAccount.objects.filter(id=patient_id).first()
#        doctor_id = userdetail.doctor[0]
#    for date in dates:
#        date = datetime.strptime(date, '%Y-%m-%d').date()
#        day_of_week = date.strftime('%A')
#        pcp_doctor = Doctor.objects.filter(id=doctor_id).first()
#        pcp_doctor_location=DoctorHospital.objects.filter(doctor_id=pcp_doctor).first()
#        doctor_availability = doctor_availability_on_Day(doctor_availability, day_of_week, date, pcp_doctor, pcp_doctor_location.location, 1)
#        res = doctor_availability_json(doctor_availability)
#        if doctor_availability!=[] and res['value']!=[]:
#            break
#    if res['value']!=[]:
#        date = res['value'][0]['slots'][0]['date']
#        date = datetime.strptime(date, '%Y-%m-%d').date()
#        day_of_week = date.strftime('%A')
#        slot_details =  res['value'][0]['slots'][0]['slot_details'][:3]
#        slot_data = ''.join('@@'+f"{slot['start_time']}@@ " for slot in slot_details)
#        return f"Dr. {pcp_doctor.first_name}  {pcp_doctor.last_name} available on {day_of_week}({date.strftime('%m-%d-%Y')}),Please select any of the available slots "+slot_data
#    else:
#       return 'No availability' 


## To find the specialization of the PCP for show the reason to the user
# @tool
# def find_specialization(doctor_id):
#     """
#     Find the specialization of a doctor based on the doctor's ID.

#     Args:
#         doctor_id (int): ID of the doctor.

#     Returns:
#         str: The specialization of the doctor, or a message if the doctor is not found.
#     """
#     try:
#         ## Retrieve the doctor by ID
#         doctor = Doctor.objects.get(id=doctor_id)
#         ## Return the specialization
#         return f"The specialization of Dr. {doctor.first_name} {doctor.last_name} is {doctor.specialization}."
#     except Doctor.DoesNotExist:
#         return f"No doctor found with ID {doctor_id}."




appointment_tools = [
    get_appointment_details,
    reschedule_appointment,
    cancel_appointment,
    # check_doctor_availability,
    # check_availability_with_dr_doctorname,
    # doctor_availability_calender,--------------
    schedule_appointment,
    # add_new_insurance,-------------------------
    # get_existing_insurance_details,-----------
    edit_insurance_details,
    change_slot,
    update_insurance_for_booked_appointment,
    # followup_appointment,----------
    # welcome_message-------------
]
