# -*- coding: utf-8 -*-
"""

Very simple acquisition with a fake multi signal device.

"""

from pyacq import StreamHandler, FakeMultiSignals

import zmq
import msgpack
import time

def test1():
    streamhandler = StreamHandler()
    
    # Configure and start
    dev = FakeMultiSignals(streamhandler = streamhandler)
    dev.configure( name = 'Test dev',
                                nb_channel = 10,
                                sampling_rate =1000.,
                                buffer_length = 6.4,
                                packet_size = 128,
                                )
    dev.initialize()
    dev.start()
    
    # Read the buffer on ZMQ socket
    port = dev.stream['port']
    np_array = dev.stream['shared_array'].to_numpy_array()
    print np_array.shape # this should be (nb_channel x buffer_length*samplign_rate)
    zmq.Context()
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE,'')
    socket.connect("tcp://localhost:{}".format(port))
    t0 = time.time()
    last_pos = 0
    while time.time()-t0<10.:
        # loop during 10s
        message = socket.recv()
        pos = msgpack.loads(message)
        # pos is absolut so need modulo
        pos2 = pos%np_array.shape[1]
        print 'pos', pos, ' time', time.time()-t0, 'np_array.shape:', np_array[:,last_pos:pos2].shape
        last_pos = pos2
        
        
    # Stope and release the device
    dev.stop()
    dev.close()



if __name__ == '__main__':
    test1()