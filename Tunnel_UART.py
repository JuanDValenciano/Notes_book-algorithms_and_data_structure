#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Universidad de ibague'e.

Author: JuanD Valenciano, jvalenciano@unal.edu.co
Date of creation: 29 june 2021
Project: AgroSensorV2.0
Target: NanoPi
Compatibility:  ---------------------------

Comments:

rsync -avz ~/GitHub/TrueVisionDev/AgroSense2.0* pi@192.168.1.35:~

    sudo rsync -avz AgroSense2.0 /opt/

    sudo python /opt/AgroSense2.0/firmware_software/ForTrueDev/app/Tunnel_UART.py /opt/AgroSense2.0/firmware_software/ForTrueDev/app/config/config_AuxUART.ini

"""
#from _typeshed import Self
import json
import serial
import signal
import subprocess
import sys
import os
import time
#import datetime
from datetime import datetime
from base64 import b64encode, b64decode
import array
import socket
import requests
import numpy as np
from ConfigParser import SafeConfigParser

import RPi.GPIO as GPIO
GPIO.setwarnings(False)

from lib.pin_out_DevBoard import *
from lib.AuxPortProtocol import *

JSON_Data2Send_Format  = '{ "idptr":"NULL", "uuid":"NULL", "lat": 4.6097100, "long" : -74.0817500, "DataBase64": "NULL"}'

JSON_NAME = 'output_TesServer.json'

REMOTE_SERVER = "www.google.com" #"unibague.edu.co" #?Si podria ser este servidor¿

API_ENDPOINT_SOCKET         = "riceclimaremote.unibague.edu.co"
API_ENDPOINT_SOCKET_PORT    = 2700

API_ENDPOINT            = "https://riceclimaremote.unibague.edu.co/controller/categoria.php?op=Insertar" 

API_SECOND2SEND         = 10

SOCKET_SEND = 1
JSON_SEND = 2
SELECTION_MODE = JSON_SEND

SAMPLE_PERIOD = 1 #Minutes
DATA_TOTAL  = 24*60 #24 Hour. 60Minutes per Hour
LENGTH_FIFO    = DATA_TOTAL*30 #Total Space to save!

class greenLed():
    """
    Class to manager green Led

    """
    def __init__(self):
        self.pin = PIN_G
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.pin , GPIO.OUT)
    def on(self):
        GPIO.output(self.pin, True)
    def off(self):
        GPIO.output(self.pin, False)
    def blinking(self, rept = 4, timeout=0.1):
        for i in range(1, rept):
            GPIO.output(self.pin, True)
            time.sleep(timeout)
            GPIO.output(self.pin, False)
            time.sleep(timeout)

class aux_com:
    """
    Class to Serial communication driver.
        Methods:
            ...........
            ...........
            ...........
    """

    def __init__(self, port, baudrate, tout, log_file, prompt_on, verbose_on):
        try:
            self.verbose_on = verbose_on
            self.log_file = log_file
            self.prompt_on = prompt_on
            self.lock = False
            self.s = serial.Serial( port, baudrate, 8, 'N', 1, timeout=tout, rtscts=False)
            if(verbose_on):
                print("> Port " + port + " opened")
            time.sleep(0.5)
        except serial.SerialException:
            if(verbose_on):
                print("> ERROR...... Init Serial port")
            sys.exit(1)

    def write( self, frame):
        self.s.write( frame)
        self.s.flush()
        #if(self.verbose_on):
        #    print("> write frame: ", frame)

    def write_chr( self, frame):
        for i in range( len(frame)):
            time.sleep(0.002)
            self.s.write( frame[i])
        self.s.flush()
    
    def write_HEX(self, frame):
        for i in range(len(frame)):
            self.s.write(chr(frame[i]))
        self.s.flush()

    def read(self):
        tmp = self.s.read()
        self.datarec = tmp
        while (tmp != ""):
            tmp = self.s.read()
            self.datarec += tmp
        if(self.verbose_on):
            for i in range(len(self.datarec)):
                print (hex(ord(self.datarec[i]))),
            print("\n")
        #if(self.verbose_on):
        #    print("> MDM Recv: ", self.datarec)

    def read_line(self):
        tmp = self.s.read()
        self.datarec = tmp
        while (tmp != ""):
            tmp = self.s.read()
            self.datarec += tmp
            if(tmp == '\r'):
                break
        if(self.verbose_on):
            print("> Recv by line: ", self.datarec)
        
    def FlushingPortIn(self):
        self.s.flushInput()

    def FlushingPortOut(self):
        self.s.flushOutput()

    def available(self):
        if(( self.s.inWaiting()) == 0):
            return 0
        else:
            return 1

    def exit(self):
        self.s.close()
        if( self.verbose_on):
            print("> Serial closed")

def is_connected(_DEBUG_ON=False):
    #now = datetime.now()
    response = -1
    ####if((now.seconds%API_SECOND2SEND)==0):
    try:
        response = os.system("ping -c 3 " + REMOTE_SERVER + " > /dev/null 2>&1") #response = os.system("ping -c 1 -W 1 -s 1 " + REMOTE_SERVER + " > /dev/null 2>&1")
        # and then check the response...
        if response == 0:
            if((verbose_on | prompt_on) & _DEBUG_ON):
                print("> is_connected try: Ok Intenet!!!!!!")  
            response = True
        else:
            if((verbose_on | prompt_on) & _DEBUG_ON):
                print("> is_connected try: No Intenet")  
            response = -1
    except:
        pass
        response = -1
        if((verbose_on | prompt_on) & _DEBUG_ON):
            print("> is_connected except pass: No Intenet")
    return response

def in_time(_time2Send, _DEBUG_ON=False):
    _delta_time = int(_time2Send)
    now = datetime.now()
    if((verbose_on | prompt_on) & _DEBUG_ON):
        print("> Date: ", now)    
    if( (now.minute%_delta_time)==0 ):
        in_times_flag=True
    else:
        in_times_flag=False
    return in_times_flag

def main():
    """

    procees recv/send data by UART:
        
    :return:

    """
    serial_com = aux_com( port, baudrate, tout, log_file, prompt_on, verbose_on)
    time.sleep(0.5)
    serial_com.FlushingPortIn()
    #serial_com.FlushingPortOut()
    GreemLED = greenLed()
    tic_timeTake = 0
    toc_timeTake = 1
    dataFails = []
    dataOther = 0
    Scheduler = 1
    try:
        while(1):
            #Task 1 Add SerialData
            if(serial_com.available()==1):
                GreemLED.on()
                if(verbose_on):
                    print("> CheckBuffer!!!!")
                time.sleep(1)
                serial_com.read()
                _ok_frame , _frameRecv = checkFrameRecv( serial_com.datarec, verbose_on)
                #serial_com.FlushingPortIn()
                if(_ok_frame == 1):
                    if(verbose_on):
                        print("> Lenght: ", len(_frameRecv))
                    _frame2Send = Set_ACK_Config(datetime.datetime.now())
                    JSON_Data2Send  = json.loads(JSON_Data2Send_Format)
                    JSON_Data2Send["idptr"] = str(idptr_Data)
                    JSON_Data2Send["uuid"]  = str(uuid_Data)
                    JSON_Data2Send["DataBase64"] = b64encode( array.array('B', _frameRecv))
                    dataStreamSend = json.dumps(JSON_Data2Send)
                    if(verbose_on):
                        print(">ACK FrameReplay: ")
                        for i in range(len( _frame2Send)):
                            print (hex(_frame2Send[i])),
                    serial_com.write_HEX( _frame2Send)
                    #serial_com.FlushingPortOut()
                    if(verbose_on):
                        print(">Add Data accumulation.")
                    numInternet = np.size(dataFails)
                    if(numInternet >= LENGTH_FIFO):
                        if(verbose_on):
                            print(">>LEGTH_FIFO")
                        dataOther+=1
                        dataFails[dataOther-1] = dataStreamSend
                        if(dataOther>=LENGTH_FIFO):
                            dataOther=0
                    else:
                        if(verbose_on):
                            print(">>LEGTH_NORMAL")
                        dataFails.append(dataStreamSend)
                    if(verbose_on & prompt_on):
                        numInternet = np.size(dataFails)
                        print(">INFO Data")
                        print(">TOTAL DATA: ", numInternet)
                        for i in range(1,numInternet+1):
                            if(verbose_on):
                                print("DATA2SEND: [", i,"]= ", dataFails[numInternet-i])
                else:
                    if(verbose_on):
                        print(">Error Recv Frame!!!: ")
                if(verbose_on):
                    print("End RecvData Serial!!!")
                Scheduler = 0
                GreemLED.off()
            #Task 2 SendData
            if((np.size(dataFails)!=0) & (Scheduler == 1)):
                if((is_connected() == True)):
                    if(verbose_on):
                        print("> OKConnection and FIFO Data!!!!")
                    numInternet = np.size(dataFails) - 1
                    try:
                        if(verbose_on):
                            print("Data2Send: ", dataFails[numInternet])
                        if(SELECTION_MODE == SOCKET_SEND):
                            if(verbose_on):
                                print("SOCKET Mode")
                            s = socket.socket()
                            s.connect(("riceclimaremote.unibague.edu.co",2700))  
                            s.send(dataFails[numInternet])
                            s.close()
                        elif(SELECTION_MODE == JSON_SEND):
                            if(verbose_on):
                                print("JSON Mode")
                            requests.post(url = API_ENDPOINT, data = dataFails[numInternet])
                        GreemLED.blinking()
                        dataFails.pop(numInternet)
                        dataOther = 0
                    except:
                        pass
                        if(verbose_on):
                            print("> Package not sent to the server!!!")
            #Task 3 KeepAlive
            if(in_time(time2Send) and tic_timeTake != toc_timeTake):    
                if(verbose_on):
                    print("> AddDataServer.......")
                tic_timeTake = datetime.now().minute
                JSON_Data2Send  = json.loads(JSON_Data2Send_Format)
                JSON_Data2Send["idptr"] = str(idptr_Data)
                JSON_Data2Send["uuid"]  = str(uuid_Data)
                dataStreamSend = json.dumps(JSON_Data2Send)
                numInternet = np.size(dataFails)
                if(numInternet >= LENGTH_FIFO):
                    if(verbose_on):
                        print(">>LEGTH_FIFO")
                    dataOther+=1
                    dataFails[dataOther-1] = dataStreamSend
                    if(dataOther>=LENGTH_FIFO):
                        dataOther=0
                else:
                    if(verbose_on):
                        print(">>LEGTH_NORMAL")
                    dataFails.append(dataStreamSend)
                if(verbose_on & prompt_on):
                    numInternet = np.size(dataFails)
                    print(">INFO Data")
                    print(">TOTAL DATA: ", numInternet)
                    for i in range(1,numInternet+1):
                        if(verbose_on):
                            print("DATA2SEND: [", i,"]= ", dataFails[numInternet-i])
                Scheduler = 0
            #Task Scheduler
            toc_timeTake = datetime.now().minute
            Scheduler = 1
            time.sleep(1) #TODO Test with diferents value
    except KeyboardInterrupt:
        serial_com.exit()
        if(verbose_on):
            print("> Exit process by interrut KeyBoard")
    except StandardError as e:
        serial_com.exit()
        if(verbose_on):
            print("> Error: ", e)

if __name__ == "__main__":
    parser = SafeConfigParser()
    parser.read(sys.argv[1])
    prompt_on = parser.getboolean('Others', 'Prompt outbound ON')
    verbose_on = parser.getboolean('Others', 'Verbose ON')
    log_file = parser.get('Others', 'Log File')
    port = parser.get('Configs', 'Port')
    baudrate = parser.get('Configs', 'Baudrate')
    tout = parser.getint('Configs', 'Serial Time Out')  # Serial port response timeout
    time2Send = parser.get('Configs', 'Time to send')
    idptr_Data = parser.get('IdDevice', 'idptr_ini') 
    uuid_Data = parser.get('IdDevice', 'uuid_ini')
    if(verbose_on):
        print('> Data config_mdm.ini:')
        print('>prompt_on: ', prompt_on)
        print('>verbose_on: ', verbose_on)
        print('>log_file: ', log_file)
        print('>port: ', port)
        print('>baudrate: ', baudrate)
        print('>tout: ', tout)
        print('>IDptr: ', idptr_Data)
        print('>UUID: ', uuid_Data)
        print('> time2Send: ', time2Send)
    try:
        main()
    finally:
        if(verbose_on):
            print('> End TunnelUART.py')
        #com_modem.exit()   #No olvidar cerrar el puerto si algo pasa.!!!!!!
        time.sleep(1)