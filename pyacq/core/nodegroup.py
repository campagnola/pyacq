from pyqtgraph.Qt import QtCore

from .rpc import RPCServer
from .node import Node

#TODO somewhere there is a list/dict of all nodes
all_nodes = { }

class RpcThread( QtCore.QThread):
    def __init__(self, parent = None):
        QtCore.QThread.__init__(self, parent)
        self.running = False
    
    def run(self):
        self.running = True
        while self.running:
            self.parent()._process_one()
    

class NodeGroup(RPCServer):
    """
    This class:
       * is a bunch of Node inside a process.
       * lauched/stoped by Host
       * able to create/delete Node (by rpc command)
       * distribute the start/stop/initialize/configure to appropriate Node
       
       
    """
    def __init__(self, name, addr):
        RPCServer.__init__(self, name, addr)
        self.nodes = {}
    
    def run_forever(self):
        self.app = QtGui.QApplication()
        self.rpc_thread = RpcThread(parent = None)
        self.rpc_thread.start()
        self.app.exec_()
    
    def delete(self):
        self.rpc_thread.running = False
        self.rpc_thread.wait()
        #TODO delete all nodes
    
    def create_node(self, name, classname, kargs):
        assert name not in self.nodes, 'This node already exists'
        node = all_nodes[classname](**kargs)
        self.nodes[name] = node
    
    def delete_node(self, name):
        node = self.nodes[name]
        assert not node.isrunning(), 'The node {} is running'.format(name)
        self.nodes.pop(node)
    
    def control_node(self, name, method, kargs):
        getattr(self.nodes[name], method(**kargs))
    
    
    def start_all(self):
        for node in self.nodes.values():
            node.start()
        
    def stop_all(self):
        for node in self.nodes.values():
            node.stop()
        
    
    