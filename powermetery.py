##!/usr/bin/python
# -*- coding: utf-8 -*-
# Sensors must be activated with "modprobe w1-gpio" and "modprobe w1-therm"!
from __future__ import division
import logging
import ssl
import websocket
import sys
import os
from threading import Timer
from time import *
logging.basicConfig()

###### logging #####
# create logger
logger = logging.getLogger('meter')
logger.setLevel(logging.ERROR) #DEBUG

# create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

fh = logging.FileHandler('/home/pi/powermeter.log')
fh.setLevel(logging.ERROR) #DEBUG
fh.setFormatter(formatter)

# create console handler and set level to debug
#ch = logging.StreamHandler()
#ch.setLevel(logging.ERROR) #DEBUG
#ch.setFormatter(formatter)

#logger.addHandler(ch)
logger.addHandler(fh)


# 1-Wire Slave-Liste
file = open('/sys/devices/w1_bus_master1/w1_master_slaves') #Verzeichniss evtl. anpassen
w1_slaves = file.readlines()
file.close()

user=0;
meterArr = [];

for line in w1_slaves:
    meterArr.append(line.rstrip())

def readMeters(addr):
    try:
       file = open('/sys/bus/w1/devices/' + str(addr) + '/w1_slave')
       filecontent = file.read()
       file.close()
    except Exception as e:
      logger.error('File read error: '+str(e))
    else:
       try:
          stringvalue = filecontent.split("\n")
       except Exception as e:
          logger.error('Parse Error 1: '+str(filecontent)+'  '+ str(e))
       else:
          try:
              if stringvalue and stringvalue[2] and stringvalue[3] and stringvalue[2].find('crc=NO')<0 and stringvalue[3].find('crc=NO')<0:
                 val1 = int(stringvalue[2].split(" c=")[1])
                 val2 = int( stringvalue[3].split(" c=")[1]);
                 return val1,val2;
              else:
                 logger.error('Parse Error 2: crc=NO')              
          except IndexError:
              logger.error('IndexError: list index out of range. 3')

# initial call
arr1 = readMeters(meterArr[0])
if arr1: meter1val1,meter1val2 = arr1
else: meter1val1,meter1val2 = None,None
arr2 = readMeters(meterArr[1])
if arr2: meter2val1,meter2val2 = arr2
else: meter2val1,meter2val2 = None,None

#meter1val1,meter1val2 = readMeters(meterArr[0])
#meter2val1,meter2val2 = readMeters(meterArr[1])

oldmin1 = meter1val1
oldmin2 = meter1val2
oldmin3 = meter2val1
oldmin4 = meter2val2

lastHrMins1={}
lastHrMins2={}
lastHrMins3={}
lastHrMins4={}

for i in [x for x in range(0, 61)]:
	# initialize dictionaries with 0 to 60 key/value pares for continuous hourly kWh calculations (for each minute updates)
    if i<10: min="0"+str(i)
    else: min=str(i)
    lastHrMins1[min]=meter1val1
    lastHrMins2[min]=meter1val2
    lastHrMins3[min]=meter2val1
    lastHrMins4[min]=meter2val2

oldday1 = meter1val1
oldday2 = meter1val2
oldday3 = meter2val1
oldday4 = meter2val2

# read 1-Wire String of S0 Counters for Meter 1 to 4 every second
def readloop():
    Timer(1.0, readloop).start()
    global oldmin1,oldmin2,oldmin3,oldmin4,oldday1,oldday2,oldday3,oldday4,lastHrMins1,lastHrMins2,lastHrMins3,lastHrMins4,meterArr

    arr1 = readMeters(meterArr[0])
    if arr1: meter1val1,meter1val2 = arr1
    else: meter1val1,meter1val2 = None,None
    arr2 = readMeters(meterArr[1])
    if arr2: meter2val1,meter2val2 = arr2
    else: meter2val1,meter2val2 = None,None

    # EACH 5 SEC check current energy generation
    if int(strftime("%S"))%5==0 :
        checkForChange(110, oldmin1, meter1val1)
        checkForChange(120, oldmin2, meter1val2)
        checkForChange(130, oldmin3, meter2val1)
        checkForChange(140, oldmin4, meter2val2)

	# fill secondly variables with current values for change detection in the next minute
    oldmin1 = meter1val1
    oldmin2 = meter1val2
    oldmin3 = meter2val1
    oldmin4 = meter2val2

    #EACH MINUTE
    if strftime("%S") == "00":
	  # check for changes in the last hour (60 times /hour)
      checkForChange(10, lastHrMins1[strftime("%M")], meter1val1)
      checkForChange(20, lastHrMins2[strftime("%M")], meter1val2)
      checkForChange(30, lastHrMins3[strftime("%M")], meter2val1)
      checkForChange(40, lastHrMins4[strftime("%M")], meter2val2)
	  
	  # save current values into dictionaries
      lastHrMins1[strftime("%M")]=meter1val1
      lastHrMins2[strftime("%M")]=meter1val2
      lastHrMins3[strftime("%M")]=meter2val1
      lastHrMins4[strftime("%M")]=meter2val2

	  # update day sums every minute
      checkForChange(60, oldday1, meter1val1)
      checkForChange(70, oldday2, meter1val2)
      checkForChange(80, oldday3, meter2val1)
      checkForChange(90, oldday4, meter2val2)

    #DAILY EXECUTION at 00.00
    if strftime("%H:%M:%S") == "23:59:59":
	  # send daily generated sum as datakey to REMROB for statistical purposes (using in widgets)
      yymm=strftime("%y%m")
      yymmdd=strftime("%y%m%d")
      sendDatakeys('counter1', meter1val1,yymm,yymmdd)
      sendDatakeys('counter2', meter1val2,yymm,yymmdd)
      sendDatakeys('counter3', meter2val1,yymm,yymmdd)
      sendDatakeys('counter4', meter2val2,yymm,yymmdd)
	  # update daily values after previous initialisation
      oldday1 = meter1val1
      oldday2 = meter1val2
      oldday3 = meter2val1
      oldday4 = meter2val2

Timer(2.0, readloop).start()

# function for checking of changes of variables
def checkForChange(varId, oldVal, meterVal):
    if isinstance(oldVal,(int,long)) and isinstance(meterVal,(int,long)) and meterVal != oldVal:
      sendInfo(varId, meterVal - oldVal)

	  
	  
# function for sending of variables to REMROB if any changed
def sendInfo(var, val):
    if ws and ws.sock: #is None
      try:
       # ws.send('{"variable":"1","value":'+str(kWmin)+'}')
        if var in [110,120,130,140]:
		  # variables for current data (5 sec updates) in WATT
          ws.send('{"variable":"'+str(var)+'" ,"value":"'+str(val)+'"}')
        else:
		  # for hourly and daily data in kWt/h
          ws.send('{"variable":"'+str(var)+'" ,"value":"'+"{0:.2f}".format(int(val)/1000)+'"}')
      except Exception as e:
        logger.error('In sendInfo ws.send broken:  '+str(e))

		
		
# function for sending of datakeys into REMROB data store
def sendDatakeys(var, val, yymm, yymmdd):
    if ws and ws.sock: #is None
      try:
        ws.send('{"datakey":"'+str(var)+'","value":'+str(val)+',"filters":{"yymm":'+yymm+',"yymmdd":'+yymmdd+'}}')
      except Exception as e:
        logger.error('In sendDatakeys ws.send broken: datakey: '+str(var)+ " value: "+str(val))
    
	    # repeat sending of data later as daily data is important for statistics
        Timer(20,sendDatakeys, [var, val, yymm, yymmdd]).start()
    else:
      Timer(20,sendDatakeys, [var, val, yymm, yymmdd]).start()


	  
##### begin Websocket #############
def on_message(ws, message):
    jsonData = json.loads(message)
    if int(jsonData["user"]) == 1:
        user=1
    else:
        user=0

authErr=0

def on_error(ws, error):
    global authErr
	# reconnect to REMROB unless the error status is 401 (Not Authorized)
    if str(error).find('401')>-1:
        logger.error("Close without restart (401) = "+ str(error))
        authErr=1;
        ws.close()
    else:
        logger.error("Closing in on_error() with restart = "+ str(error))

#todo update ws-client v 0.33.0
#    if isinstance(error, WebSocketBadStatusException):
#      status = error.status_code
#      print('status', status)

def on_close(ws):
    global authErr
    logger.info("... closed ...")
    if authErr ==0 : Timer(10.0, startSocket).start()

start = 1
def on_open(ws):
    logger.info("... ws opend ...")
    global start,meter1val1,meter1val2,meter2val1,meter2val2
    global oldmin1,oldmin2,oldmin3,oldmin4,oldday1,oldday2,oldday3,oldday4,lastHrMins1,lastHrMins2,lastHrMins3,lastHrMins4

    ####### send initializing values ##########
    if start==1:
        sendInfo(10, meter1val1-lastHrMins1[strftime("%M")])
        sendInfo(20, meter1val2-lastHrMins2[strftime("%M")])
        sendInfo(30, meter2val1-lastHrMins3[strftime("%M")])
        sendInfo(40, meter2val2-lastHrMins4[strftime("%M")])

        sendInfo(60, meter1val1-oldday1)
        sendInfo(70, meter1val2-oldday2)
        sendInfo(80, meter2val1-oldday3)
        sendInfo(90, meter2val2-oldday4)

        sendInfo(110, meter1val1-oldmin1)
        sendInfo(120, meter1val2-oldmin2)
        sendInfo(130, meter2val1-oldmin3)
        sendInfo(140, meter2val2-oldmin4)
	    
        start = 0

ws = websocket.WebSocketApp('wss://objects.remrob.com/v1/?model=xxx&id=xxx&key=xxxxx', on_error = on_error, on_close = on_close)

ws.on_open = on_open

def startSocket():
    ws.run_forever()

startSocket()
