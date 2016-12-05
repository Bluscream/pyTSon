from ts3plugin import ts3plugin

import ts3, ts3defines
import os

from PythonQt.QtNetwork import QLocalServer
from PythonQt.QtCore import QByteArray

class ipcdata(object):
    longlen = 5

    def __init__(self, *, init=None, obj=None):
        self.buf = init if init else bytes()
        self.pos = 0

        if obj:
            self.append(obj)

    def append(self, obj):
        if type(obj) is str:
            d = bytes(obj, 'utf-8')
            self.buf += b's'
            self.buf += len(d).to_bytes(self.longlen, byteorder='big')
            self.buf += d
        elif type(obj) is int:
            self.buf += b'i'
            self.buf += obj.to_bytes(self.longlen, byteorder='big')
        elif type(obj) is list or type(obj) is tuple:
            self.buf += b'l' if type(obj) is list else b't'
            self.buf += len(obj).to_bytes(self.longlen, byteorder='big')
            for e in obj:
                self.append(e)
        else:
            raise Exception("Unknown ipcdata type")

    def read(self):
        t = chr(self.buf[self.pos])
        self.pos += 1

        if t == "s":
            self.pos += self.longlen
            l = int.from_bytes(self.buf[self.pos - self.longlen:self.pos], byteorder='big')
            spos = self.pos
            self.pos += l
            return self.buf[spos:self.pos].decode('utf-8')
        elif t == "i":
            self.pos += self.longlen
            return int.from_bytes(self.buf[self.pos - self.longlen:self.pos], byteorder='big')
        elif t == "l" or t == "t":
            ret = []
            self.pos += self.longlen
            l = int.from_bytes(self.buf[self.pos - self.longlen:self.pos], byteorder='big')

            for i in range(l):
                ret.append(self.read())

            return ret if t == "l" else tuple(ret)

    def readAll(self, fromstart=False):
        if fromstart:
            self.pos = 0

        while not self.atEnd():
            yield self.read()

    def atEnd(self):
        return self.pos == len(self.buf)

    @property
    def data(self):
        return self.buf

    def __iadd__(self, other):
        self.append(other)
        return self


class ipcplugin(ts3plugin):
    requestAutoload = False
    name = "ipc"
    version = "1.0"
    apiVersion = 21
    author = "Thomas \"PLuS\" Pathmann"
    description = "This is a plugin used for interprocess communication. It broadcasts events to clients and can receive commands to execute."
    offersConfigure = False
    commandKeyword = ""
    infoTitle = None
    menuItems = []
    hotkeys = []

    def __init__(self):
        self.clients = []

        self.server = QLocalServer()
        self.server.connect("newConnection()", self.onNewConnection)

        path = os.path.join(ts3.getPluginPath(), "pyTSon", "ipcsocket")
        QLocalServer.removeServer(path)
        if not self.server.listen(path):
            raise Exception("Error opening local socket (%s)" % path)

    def stop(self):
        for cli in self.clients:
            cli.disconnectFromServer()

        self.server.close()
        self.server.delete()

    def onNewConnection(self):
        cli = self.server.nextPendingConnection()
        cli.connect("readyRead()", lambda: self.onClientData(cli))
        cli.connect("disconnected()", lambda: self.onClientDisconnected(cli))

        self.clients.append(cli)

    def onClientData(self, cli):
        data = ipcdata(init=cli.read(cli.bytesAvailable()).data())
        name = data.read()

        if hasattr(ts3, name):
            args = []
            while not data.atEnd():
                args.append(data.read())

            ret = getattr(ts3, name)(*args)

            if ret:
                cli.write(QByteArray(ipcdata(obj=ret).data))
        else:
            err = ts3.logMessage("Unknown method data %s" % data.data, ts3defines.LogLevel.LogLevel_ERROR, "pyTSon.ipcplugin", 0)
            if err != ts3defines.ERROR_ok:
                print("Unknown method data in ipcplugin: %s" % data.data)

    def onClientDisconnected(self, cli):
        self.clients.remove(cli)

    def send(self, bytestr):
        for cli in self.clients:
            cli.write(QByteArray(bytestr))

    def callback(self, name, *args):
        data = ipcdata(obj=name)

        for p in args:
            data.append(p)

        self.send(data.data)

    def __getattr__(self, name):
        return (lambda *args: self.callback(name, *args))


"""
Example PyQt python client:
class ipcclient(object):
    def __init__(self, path):
        self.incmd = False

        self.socket = QLocalSocket()
        self.socket.readyRead.connect(self.onReadyRead)
        self.socket.connectToServer(path)

        if not self.socket.waitForConnected(1000):
            raise Exception("Error connecting to socket on %s" % path)

    def onReadyRead(self):
        if self.incmd:
            return

        data = ipcdata(init=self.socket.read(self.socket.bytesAvailable()))
        name = data.read()

        if hasattr(self, name):
            getattr(self, name)(*tuple(data.readAll()))

    def function(self, name, *args):
        if self.socket.state() != QLocalSocket.ConnectedState:
            raise Exception("Socket is not connected")

        data = ipcdata(obj=name)

        for p in args:
            data.append(p)

        self.incmd = True
        self.socket.write(data.data)
        if self.socket.waitForBytesWritten(1000):
            if self.socket.waitForReadyRead(5000):
                data = ipcdata(init=self.socket.read(self.socket.bytesAvailable()))
                self.incmd = False
                return data.read()
            else:
                self.incmd = False
                raise Exception("Socket timed out waiting for answer")
        else:
            self.incmd = False
            raise Exception("Socket timed out during write process")

    def __getattr__(self, name):
        return (lambda *args: self.function(name, *args))

class myclient(ipcclient):
    def onTalkStatusChangeEvent(self, serverConnectionHandlerID, status, isReceivedWhisper, clientID):
        print("talkstatus %s %s %s" % (serverConnectionHandlerID, status, clientID))
"""

