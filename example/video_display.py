import numpy as np
from pyacq import create_manager, ImageViewer, FakeVideoSource
from pyqtgraph.Qt import QtCore, QtGui



#view is a Node in local QApp
app = QtGui.QApplication([])

data = np.random.normal(size=(10, 100, 100))

source = FakeVideoSource()

viewer = ImageViewer(gfxlib='vispy')
viewer.configure()
viewer.input.connect(source.output)
viewer.initialize()
viewer.show()

source.start()
viewer.start()

app.exec_()
