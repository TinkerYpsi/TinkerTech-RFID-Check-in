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

def get_user_data(rfid_tag_id):
    #See Google Sheets API python documentation
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
            range='A2:M').execute()
    values = result.get('values', [])
    
    for row in values:
        print(len(values))
        if rfid_tag_id == row[0]:
            print("Authentication succeeded!")
            print(row)

            #Send to WebUI via flask_socketio
            socketio.emit('rfid_scanned',
                    {'rfid':row[0],'name':row[1],'membership':row[2],'enrolled':row[3],'credit':row[4],'tools':row[5]})

def enroll_user(user_info):
    print("Enrolling user with data: " + user_info)
    sheet.add_rows(['id','name','membership','credit','tools'],0)

def rfid_read_loop():
    print("Starting RFID read loop!")
    while True:
        try:
            #Read user id from RFID reader, print to console
            user_id, text = reader.read()
            user_id = str(user_id)
            print(user_id)

            #Request data from Google Sheets
            get_user_data(user_id)
        except KeyboardInterrupt:
            print("Quitting...")
            GPIO.cleanup()
            sys.exit()



#Flask routes
@app.route('/')
def index_route():
    return render_template('index.html')

@socketio.on('enroll_user')
def socket_enroll(user_info):
    enroll_user(user_info)


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
