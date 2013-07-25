# -*- coding: utf-8 -*-

import multiprocessing as mp
import numpy as np
import msgpack
import time

import zmq

import os
from collections import OrderedDict

from .base import DeviceBase
#~ from ..tools import SharedArray

import ctypes
from ctypes import byref


## Wrapper on Universal Library with ctypes with error handling
try:
    _cbw = ctypes.windll.cbw32
    print 'cbw32'
except WindowsError:
    _cbw = ctypes.windll.cbw64
    #~ _cbw = ctypes.WinDLL('cbw64.dll')
    print 'cbw64'

class ULError( Exception ):
    def __init__(self, errno):
        self.errno = errno
        err_msg = ctypes.create_string_buffer(UL.ERRSTRLEN)
        errno2 = _cbw.cbGetErrMsg(errno,err_msg)
        assert errno2==0, Exception('_cbw.cbGetErrMsg do not work')
        errstr = 'ULError %d: %s'%(errno,err_msg.value)                
        Exception.__init__(self, errstr)

def decorate_with_error(f):
    def func_with_error(*args):
        errno = f(*args)
        if errno!=UL.NOERRORS:
            raise ULError(errno)
        #~ assert errno==0, ULError(errno)
        return errno
    return func_with_error

class CBW:
    def __getattr__(self, attr):
        f = getattr(_cbw, attr)
        return decorate_with_error(f)

cbw = CBW()    
##



def device_mainLoop(stop_flag, streams, board_num):
    streamAD = streams[0]
    
    packet_size = streamAD['packet_size']
    sampling_rate = streamAD['sampling_rate']
    np_arr = streamAD['shared_array'].to_numpy_array()
    nb_total_channel = streamAD['nb_channel'] + 0 # +3
    nb_channel_ad = streamAD['nb_channel']
    half_size = np_arr.shape[1]/2

    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind("tcp://*:{}".format(streamAD['port']))

    
    #~ chan_array = np.array( range(64)+[UL.FIRSTPORTA, UL.FIRSTPORTB, UL.FIRSTPORTC], dtype = np.int16)
    chan_array = np.array( streamAD['channel_indexes'], dtype = np.int16)# +[UL.FIRSTPORTA, UL.FIRSTPORTB, UL.FIRSTPORTC], dtype = np.int16)
    chan_array_type = np.array( [UL.ANALOG] * nb_channel_ad, dtype = np.int16)   #+[ UL.DIGITAL8] * 3
    gain_array = np.array( [UL.BIP10VOLTS] *nb_channel_ad, dtype = np.int16)
    real_sr = ctypes.c_long(int(sampling_rate))
    # FIXME buffer size
    internal_size = int(30.*sampling_rate)
    internal_size = internal_size- internal_size%packet_size
    print internal_size
    int16_arr = np.zeros(( internal_size, nb_total_channel), dtype = np.uint16)
    pretrig_count = ctypes.c_long(0)
    total_count = ctypes.c_long(int(int16_arr.size))
    # FIXME try with other card
    options = UL.BACKGROUND + UL.BLOCKIO  + UL.CONTINUOUS + UL.CONVERTDATA
    #~ options = UL.BACKGROUND + UL.DMAIO  + UL.CONTINUOUS + UL.CONVERTDATA
    #~ options = UL.BACKGROUND  + UL.CONTINUOUS + UL.CONVERTDATA
    
    try:
        # this is SLOW!!!!:
        cbw.cbDaqInScan(board_num, chan_array.ctypes.data,  chan_array_type.ctypes.data,
                            gain_array.ctypes.data, nb_total_channel, byref(real_sr), byref(pretrig_count),
                             byref(total_count) ,int16_arr.ctypes.data, options)
    except ULError as e:
        print e
        print 'not able to cbDaqInScan properly'
        return
    
    status = ctypes.c_int(0)
    cur_count = ctypes.c_long(0)
    cur_index = ctypes.c_long(0)
    function = UL.DAQIFUNCTION
    
    # TODO this
    dict_gain = {UL.BIP10VOLTS: [-10., 10.],
                        UL.BIP1VOLTS: [-1., 1.],
                        }
    low_range = np.array([ dict_gain[g][0] for g in gain_array ])
    hight_range = np.array([ dict_gain[g][1] for g in gain_array ])
    buffer_gains = 1./(2**16)*(hight_range-low_range)
    buffer_gains = buffer_gains[ :, np.newaxis]
    buffer_offsets = low_range
    buffer_offsets = buffer_offsets[ :, np.newaxis]
    
    pos = abs_pos = 0
    last_index = 0
    
    
    while True:
        #~ try:
        if True:
            cbw.cbGetIOStatus( ctypes.c_int(board_num), byref(status),
                      byref(cur_count), byref(cur_index), ctypes.c_int(function))
            
            index = cur_index.value/nb_channel_ad
            if index ==-1: continue
            if index == last_index : 
                continue
            t1 = time.time()
            if index<last_index:
                new_size = int16_arr.shape[0] - last_index
                
                np_arr[:,pos:pos+new_size] = int16_arr[last_index:, :].transpose()
                np_arr[:,pos:pos+new_size] *= buffer_gains
                np_arr[:,pos:pos+new_size] += buffer_offsets
                
                end = min(pos+half_size+new_size, np_arr.shape[0])
                new_size = min(new_size, np_arr.shape[1]-(pos+half_size))
                np_arr[:,pos+half_size:pos+half_size+new_size] = int16_arr[ last_index:last_index+new_size, :].transpose()
                np_arr[:,pos+half_size:pos+half_size+new_size] *= buffer_gains
                np_arr[:,pos+half_size:pos+half_size+new_size] += buffer_offsets
                
                abs_pos += new_size
                pos = abs_pos%half_size
                last_index = 0

            new_size = index - last_index
            
            np_arr[:,pos:pos+new_size] = int16_arr[ last_index:index, : ].transpose()
            np_arr[:,pos:pos+new_size] *= buffer_gains
            np_arr[:,pos:pos+new_size] += buffer_offsets
            
            new_size = min(new_size, np_arr.shape[1]-(pos+half_size))
            np_arr[:,pos+half_size:pos+new_size+half_size] = int16_arr[ last_index:last_index+new_size, : ].transpose()
            np_arr[:,pos+half_size:pos+new_size+half_size] *= buffer_gains
            np_arr[:,pos+half_size:pos+new_size+half_size] += buffer_offsets
            
            abs_pos += new_size
            pos = abs_pos%half_size
            last_index = index

            
            abs_pos += index - last_index
            socket.send(msgpack.dumps(abs_pos))
            
            last_index = index
        #~ except ULError as e:
            #~ print 'Problem ULError in acquisition loop', e
            #~ break
        #~ except :
            #~ print 'Problem in acquisition loop'
            #~ break
            
        if stop_flag.value:
            print 'should stop properly'
            break
        t2 = time.time()
        #~ time.sleep(packet_size/sampling_rate)
        #~ print t2-t1, max(packet_size/sampling_rate-(t2-t1) , 0) , packet_size/sampling_rate
        #~ print 'sleep', packet_size/sampling_rate-(t2-t1), packet_size/sampling_rate, t2-t1
        time.sleep(max(packet_size/sampling_rate-(t2-t1), 0))
        #~ print 'half sleep'
        
    try:
        cbw.cbStopBackground(board_num, function)
        print 'has stop properly'
    except ULError:
        print 'not able to stop cbStopBackground properly'
        
        #~ time.sleep(packet_size/sampling_rate)
        #~ gevent.sleep(packet_size/sampling_rate)



def get_info(board_num):
    
    config_val = ctypes.c_int(0)
    l = [ ('nb_channel_ad', UL.BOARDINFO, UL.BINUMADCHANS),
                ('nb_channel_da', UL.BOARDINFO, UL.BINUMDACHANS),
                ('BINUMIOPORTS', UL.BOARDINFO, UL.BINUMIOPORTS),
                ('nb_channel_dig', UL.BOARDINFO, UL.BIDINUMDEVS),
                ('serial_num', UL.BOARDINFO, UL.BISERIALNUM),
                ('factory_id', UL.BOARDINFO, UL.BIFACTORYID),
                ]
    info = {'board_num' : board_num}
    board_name = ctypes.create_string_buffer(UL.BOARDNAMELEN)
    cbw.cbGetBoardName(board_num, byref(board_name))# this is very SLOW!!!!!!!
    
    info['board_name'] = board_name.value
    for name, info_type, config_item in l:
        cbw.cbGetConfig(info_type, board_num, 0, config_item, byref(config_val))
        info[name] = config_val.value
    
    dict_packet_size = 	{
                "USB-1616FS"  : 62,
                "USB-1208LS" : 64,
                "USB-1608FS" : 31,
                'PCI-1602/16' : 64,
                }
    info['device_packet_size'] = dict_packet_size.get(info['board_name'], 512)
    
    return info

class MeasurementComputingMultiSignals(DeviceBase):
    """
    Usage:
        dev = MeasurementComputingMultiSignals()
        dev.configure(board_num = 0)
        dev.initialize()
        dev.start()
        dev.stop()
        
    Configuration Parameters:
        board_num
        sampling_rate
        buffer_length
        channel_names
        channel_indexes
    """
    def __init__(self,  **kargs):
        DeviceBase.__init__(self, **kargs)
    
    @classmethod
    def get_available_devices(cls):
        print cls
        devices = OrderedDict()
        
        
        config_val = ctypes.c_int(0)
        cbw.cbGetConfig(UL.GLOBALINFO, 0, 0, UL.GINUMBOARDS, byref(config_val))
        board_nums = config_val.value
        for board_num in range(board_nums):
            try:
                info = get_info(board_num)
                devices[board_num] = info
            except ULError:
                pass
        
        return devices

    def configure(self, board_num = 0, 
                                    channel_indexes = None,
                                    channel_names = None,
                                    buffer_length= 5.12,
                                     sampling_rate =1000.,
                                    ):
        self.params = {'board_num' : board_num,
                                'channel_indexes' : channel_indexes,
                                'channel_names' : channel_names,
                                'buffer_length' : buffer_length,
                                'sampling_rate' : sampling_rate
                                }
        self.__dict__.update(self.params)
        self.configured = True

    def initialize(self, streamhandler = None):
        
        self.sampling_rate = float(self.sampling_rate)
        
        # TODO card by card
        info = self.device_info = get_info(self.board_num)
        
        if self.channel_indexes is None:
            self.channel_indexes = range(info['nb_channel_ad'])
        if self.channel_names is None:
            self.channel_names = [ 'Channel {}'.format(i) for i in self.channel_indexes]
        self.nb_channel = len(self.channel_indexes)
        self.packet_size = int(info['device_packet_size']/self.nb_channel)
        print 'self.packet_size', self.packet_size
        
        
        l = int(self.sampling_rate*self.buffer_length)
        self.buffer_length = (l - l%self.packet_size)/self.sampling_rate
        #~ print 'buffer_length', self.buffer_length
        self.name = '{} #{}'.format(info['board_name'], info['factory_id'])
        s  = self.streamhandler.new_signals_stream(name = self.name, sampling_rate = self.sampling_rate,
                                                        nb_channel = self.nb_channel, buffer_length = self.buffer_length,
                                                        packet_size = self.packet_size, dtype = np.float64,
                                                        channel_names = self.channel_names, channel_indexes = self.channel_indexes,            
                                                        )
        self.streams = [s, ]

        arr_size = s['shared_array'].shape[1]
        assert (arr_size/2)%self.packet_size ==0, 'buffer should be a multilple of pcket_size {}/2 {}'.format(arr_size, self.packet_size)
        
        
    
    def start(self):
        self.stop_flag = mp.Value('i', 0)
        
        
        #~ mp_arr = s['shared_array'].mp_array
        self.process = mp.Process(target = device_mainLoop,  args=(self.stop_flag, self.streams, self.board_num) )
        self.process.start()
        
        print 'MeasurementComputingMultiSignals started:', self.name
        self.running = True
    
    def stop(self):
        self.stop_flag.value = 1
        self.process.join()
        print 'MeasurementComputingMultiSignals stopped:', self.name
        
        self.running = False
    
    def close(self):
        pass
        #TODO release stream and close the device



def generate_ULconstants():
    print 'generate_ULconstants' 
    print __file__
    print os.path.dirname(__file__)
    target = os.path.join(os.path.dirname(__file__), 'ULconstants.py')
    source = os.path.join(os.path.dirname(__file__), 'cbw.h')
    assert os.path.exists(source), 'Put cbw.h file in the pyacq/core/device'

    import re

    fid = open(target,'w')
    fid.write('# this file is generated : do not modify\n')
    for line in open(source,'r').readlines():
        #~ if 'cb' in line:
            #~ continue
        if '#define cbGetStatus cbGetIOStatus' in line :
            continue
        if '#define cbStopBackground cbStopIOBackground' in line :
            continue
        if 'float' in line or 'int' in line or 'char' in line or 'long' in line or 'short' in line \
                or 'HGLOBAL' in line \
                or 'USHORT' in line or 'LONG' in line  \
                or '#endif' in line or  '#undef' in line or  '#endif' in line \
                or 'EXTCCONV' in line :
            continue
        
        r = re.findall('#define[ \t]*(\S*)[ \t]*(\S*)[ \t]*/\* ([ \S]+) \*/',line)
        if len(r) >0:
            fid.write('%s    =    %s    # %s \n'%r[0])
            continue

        r = re.findall('#define[ \t]*(\S*)[ \t]*(\S*)[ \t]*',line)
        if len(r) >0:
            fid.write('%s    =    %s    \n'%r[0])
            continue

        r = re.findall('/\* ([ \S]+) \*/',line)
        if len(r) >0:
            comments = r[0]
            fid.write('# %s \n'%comments)
            continue
        
        if line == '\r\n':
            fid.write('\n')
            continue
        
        if '(' in line and ')' in line :
            continue
        #~ print len(line),line
    fid.close()

try :
    from  . import ULconstants as UL
except:
    generate_ULconstants()
    #~ import .ULconstants as UL 
    from  . import ULconstants as UL


