# This file is part of collectdagent.
#
#   collectdagent is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 2 of the License, or
#   (at your option) any later version.
#
#   collectdagent is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with collectdagent.  If not, see <http://www.gnu.org/licenses/>.


#
# This set of imports is required to run as a Windows service
#
from os.path import splitext, abspath
from sys import modules, executable
from time import *
import win32serviceutil
import win32service
import win32event
import win32api
#
# This set of imports is required for the agent
#
import collectdagent

#
# The section below is required for Windows services
#
class CollectdAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'collegtagent'
    _svc_display_name_ = 'Collectd Agent'
    _svc_description_ = 'Agent to send statistics to collectd'
    worker = None
        
    def __init__(self, *args):
        win32serviceutil.ServiceFramework.__init__(self, *args)
        self.log('init')
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.worker = Agent()

    def log(self, msg):
        import servicemanager
        servicemanager.LogInfoMsg(str(msg))
       
    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
        try:
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self.log('start')
            self.worker.MainLoop()
            self.log('wait')
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
            self.log('done')
        except Exception, x:
            self.log('Exception : %s' % x)
            self.SvcStop()
    
    def SvcStop(self):
        self.log('start')
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.worker.StopLoop()
        win32event.SetEvent(self.stop_event)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)
        self.log('stop')
       
if __name__ == '__main__':
     win32serviceutil.HandleCommandLine(CollectdAgentService)
