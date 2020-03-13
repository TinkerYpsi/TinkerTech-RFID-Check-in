#!/user/bin/env python

print("Initializing...")

import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

import json
import signal
import sys
import time
import pickle
import os
from multiprocessing import Process, Value
from threading import Thread
import urllib.request

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from flask import Flask, render_template
from flask_socketio import SocketIO, emit

from datetime import datetime


# Initialize RFID reader
reader = SimpleMFRC522()
user_id = ''

#Initialize Flask (Python web server library)
app = Flask(__name__)
app.config['SECRET_KEY'] = 'tinker' #See: https://github.com/miguelgrinberg/Flask-SocketIO
socketio = SocketIO(app)

# Initialize google sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '1IAjIoVfCKACg5cpOJytSwX8MXdQ1l53VXtswyJtDYDk'

print("Authenticating with Google Sheets API...")
# --- See https://developers.google.com/sheets/api/quickstart/python ---
creds = None
# The file token.pickle stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        creds = pickle.load(token)
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_console()#flow.run_local_server(port=0,host='10.10.24.20')
    # Save the credentials for the next run
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)

service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()
# --- ---
print("Authentication finished!")

last_user_info = None
to_enroll_data = None
def get_user_data(rfid_tag_id):
    global to_enroll_data
    global last_user_info

    #See Google Sheets API python documentation
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
            range='A2:M').execute()
    values = result.get('values', [])
    
    print("To enroll data: " + str(to_enroll_data))

    for i in range(len(values)):
        row = values[i]
        print(len(values))
        if rfid_tag_id == row[0]:
            print("Authentication succeeded!")
            print(row)

            if to_enroll_data != None:
                #Update user
                to_enroll_data['rfid'] = rfid_tag_id
                update_user(to_enroll_data, i)
                to_enroll_data = None
            else:
                #Send to WebUI via flask_socketio
                last_user_info = {'rfid':row[0],'name':row[1],'membership':row[2],'duration':row[3],'enrolled':row[4],'expiration':row[5],'credit':row[6],'tools':row[7],'visit':row[8]}
                socketio.emit('rfid_scanned',last_user_info)

                update_visit_time(i)
            return

    if to_enroll_data != None:
        to_enroll_data['rfid'] = rfid_tag_id
        enroll_user(to_enroll_data)
        to_enroll_data = None
    else:
        socketio.emit('rfid_unknown',{})

def update_visit_time(row):
    print("Updating user's last visit time...")

    #Writing data to sheet
    range_ = 'I'+str(row+2)+':I'+str(row+2)
    print("Updating range: " + range_)
    today = datetime.now().strftime("%Y-%m-%d %I:%M %p")

    times = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_).execute()['values'][0][0]
    print(times)

    body_ = {"range":range_,"majorDimension":"ROWS","values": [[today+", "+times]]}
    
    #Then update them
    request = service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, valueInputOption="RAW",range=range_,body=body_)
    response = request.execute()
    print(response)

def enroll_user(user_info):
    print("Enrolling user with data (writing to new row in spreadsheet): " + str(user_info))
    today = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    user_info_list = [user_info['rfid'],user_info['name'],user_info['membership'],user_info['duration'],user_info['enrolled'],user_info['expiration'],user_info['credit'],user_info['tools'],today]

    #Writing data to sheet
    body_ = {"range":"A2:M","majorDimension":"ROWS","values": [user_info_list]}
    request = service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range='A2:M', insertDataOption="INSERT_ROWS", valueInputOption="RAW", body=body_)
    response = request.execute()
    print(response)

    socketio.emit('rfid_enrolled',{})

def update_user(user_info, row):
    print("Updating user with data (updating row in spreadsheet): " + str(user_info))
    user_info_list = [user_info['rfid'],user_info['name'],user_info['membership'],user_info['duration'],user_info['enrolled'],user_info['expiration'],user_info['credit'],user_info['tools']]

    #Writing data to sheet
    range_ = 'A'+str(row+2)+':M'+str(row+2)
    print("Updating range: " + range_)
    body_ = {"range":range_,"majorDimension":"ROWS","values": [user_info_list]}
    
    #Then update them
    request = service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, valueInputOption="RAW",range=range_,body=body_)
    response = request.execute()
    print(response)

    socketio.emit('rfid_enrolled',{})

def rfid_read_loop():
    print("Starting RFID read loop!")
    while True:
        try:
            #Read user id from RFID reader, print to console
            user_id, text = reader.read()
            user_id = str(user_id)
            print("RFID Tag scanned: " + user_id)

            #Request data from Google Sheets
            socketio.emit('rfid_loading',{})
            get_user_data(user_id)
        except KeyboardInterrupt:
            print("Quitting...")
            GPIO.cleanup()
            sys.exit()



#Flask routes
@app.route('/')
def index_route():
    return render_template('index.html')

@app.route('/enroll')
def enroll_route():
    return render_template('enroll.html',title='RFID Enrollment', name='', membership='individual', duration='month', credit='0', enrolled=datetime.now().strftime("%Y-%m-%d"), tools='')

@app.route('/update')
def update_route():
    global last_user_info

    if last_user_info != None:
        return render_template('enroll.html',title='Update User', **last_user_info)

@socketio.on('enroll_user')
def socket_enroll(user_info):
    global to_enroll_data
    
    print("Enrollment data sent, waiting for RFID scan!")
    socketio.emit('rfid_waiting',{})
    to_enroll_data = user_info

if __name__ == "__main__":
    #Run RFID loop in seperate thread
    rfid_process = Thread(target=rfid_read_loop)
    rfid_process.daemon = True
    rfid_process.start()

    print("Starting Flask web server!")
    socketio.run(app,host="0.0.0.0")

GPIO.cleanup()

#url = 'http://www.tinkertech.io/IoT/users.txt'
#data = urllib.request.urlopen(url)
#
#for line in data:
#	this_id = line.decode('utf-8').strip()
#	print(this_id)
#	if this_id == str(user_id):
#		print('Thanks for checking in!')
