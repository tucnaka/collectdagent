# This file is part of collectdagent.^M
#^M
#   collectdagent is free software: you can redistribute it and/or modify^M
#   it under the terms of the GNU General Public License as published by^M
#   the Free Software Foundation, either version 2 of the License, or^M
#   (at your option) any later version.^M
#^M
#   collectdagent is distributed in the hope that it will be useful,^M
#   but WITHOUT ANY WARRANTY; without even the implied warranty of^M
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the^M
#   GNU General Public License for more details.^M
#^M
#   You should have received a copy of the GNU General Public License^M
#   along with collectdagent.  If not, see <http://www.gnu.org/licenses/>.^M

#
# This set of imports is required for the agent
#
import psutil
import sys
import re
import os
import socket
import time
import struct
import traceback

waittime = 60
walltime = int(time.time())
hostname = socket.gethostname()
hostname = hostname.lower()

TYPE_HOST            = 0x0000
TYPE_TIME            = 0x0001
TYPE_PLUGIN          = 0x0002
TYPE_PLUGIN_INSTANCE = 0x0003
TYPE_TYPE            = 0x0004
TYPE_TYPE_INSTANCE   = 0x0005
TYPE_VALUES          = 0x0006
TYPE_INTERVAL        = 0x0007

VALUE_COUNTER  = 0
VALUE_GAUGE    = 1
VALUE_DERIVE   = 2
VALUE_ABSOLUTE = 3

class Logging:
    LOG_DEBUG   = 0
    LOG_INFO    = 1
    LOG_NOTICE  = 2
    LOG_WARNING = 3
    LOG_ERROR   = 4
    logfile = "C:\Python27\collect-adgent.log"
    min_level = LOG_DEBUG
    logging = None
    
    def logit(self, message, level = LOG_DEBUG):
        if (level <= self.min_level):
            print "%s %s" %(time.ctime(), message), logging
    
    def __init__(self, filename = logfile, level = LOG_DEBUG):
        self.logfile = filename
        self.min_level = level
        if filename == '-':
            self.logging = STDOUT
        else:
            self.logging = open(filename, "a")

class Collect:
    string_codes = [TYPE_HOST, TYPE_PLUGIN, TYPE_PLUGIN_INSTANCE, TYPE_TYPE, TYPE_TYPE_INSTANCE]
    number_codes = [TYPE_TIME, TYPE_INTERVAL]

    value_format = {
        VALUE_COUNTER:  "!Q",
        VALUE_GAUGE:    "<d",
        VALUE_DERIVE:   "!q",
        VALUE_ABSOLUTE: "!Q"
    }

    def packNumeric(self, type_code, number):
        return struct.pack("!HHq", type_code, 2 + 2 + 8, number)

    def packString(self, type_code, string):
        return struct.pack("!HH", type_code, 2 + 2 + len(string) + 1) + string + "\0"

    def pack(self, id, value):
        if id in self.number_codes:
            return self.packNumeric(id, value)
        elif id in self.string_codes:
            return self.packString(id, value)
        else:
            raise AssertionError("pack(id=%d,value=%lx):invalid type code" % (id, value))


    def messageHeader(self, plugin_name, host = hostname, when = walltime, interval = waittime):
        base = "".join([
            self.pack(TYPE_HOST, host),
            self.pack(TYPE_TIME, when),
            self.pack(TYPE_PLUGIN, plugin_name),
            self.pack(TYPE_INTERVAL, interval)])
        return base

    #
    # The collectd protocol does not expect multiple type-value pairs
    # to be presented in a series together (i.e. (type,value)(type,value)
    # but rather as a series of types and then values -
    # i.e. (type1,type2,value1,value2)
    # Whilst everything is constant length and header formulation is easy,
    # the payload needs to be enumerated slightly differently.
    #
    def packValues(self, *pairs):
        types = []
        values = []
        for [type, value] in pairs:
            types.append(struct.pack("<B", type))
            values.append(struct.pack(self.value_format[type], value))
        #
        # A curious mind why ask "1 + 8" - this represents that there is both
        # a type (8 bit) and value (64 bit) pair that needs to be stored for
        # each value
        #
        buffer = struct.pack("!HHH", TYPE_VALUES, 6 + len(types) * (1 + 8), len(pairs))
        for i in types:
            buffer = "".join([buffer, i])
        for i in values:
            buffer = "".join([buffer, i])
        return buffer

    def __init__(self):
        pass

class CollectdAgent:
    sendsock = None
    logger = None
    server = ""
    portnum = 0
    ps = None
    C = None

    def sendMessage(self, message):
        self.sendsock.sendto(message, (self.server, self.portnum))
 
    #
    # Exceptions from psutil can occur at random times, for example a drive being unmounted
    # between certain lines of code or failing for an internal reason. In some instances the
    # error should be seen as potentially transient, others left to cause a fault. Similarly
    # socket exceptions are ignored as anything that might happen to cause one is likely to
    # be fatal enough to require restarting. Given this, exceptions are caught in the main
    # loop so that they can be logged.
    #
    
    def reportCPU(self):
        i = 0
        header = self.C.messageHeader("cpu")
        buffer = header
        cpus = psutil.cpu_times_percent(percpu=True)

        for cpu in cpus:
            data = self.C.pack(TYPE_PLUGIN_INSTANCE, str(i))
            data = "".join([data, self.C.pack(TYPE_TYPE_INSTANCE, "idle")])
            data = "".join([data, self.C.pack(TYPE_TYPE, "percent")])
            data = "".join([data, self.C.packValues([VALUE_GAUGE, int(cpu.idle)])])
            data = "".join([data, self.C.pack(TYPE_TYPE_INSTANCE, "user")])
            data = "".join([data, self.C.pack(TYPE_TYPE, "percent")])
            data = "".join([data, self.C.packValues([VALUE_GAUGE, int(cpu.user)])])
            data = "".join([data, self.C.pack(TYPE_TYPE_INSTANCE, "interrupt")])
            data = "".join([data, self.C.pack(TYPE_TYPE, "percent")])
            data = "".join([data, self.C.packValues([VALUE_GAUGE, int(cpu.interrupt)])])
            data = "".join([data, self.C.pack(TYPE_TYPE_INSTANCE, "system")])
            data = "".join([data, self.C.pack(TYPE_TYPE, "percent")])
            data = "".join([data, self.C.packValues([VALUE_GAUGE, int(cpu.system)])])
            i = i + 1
            if len(buffer) + len(data) > 1400:
                self.sendMessage(buffer)
                buffer = "".join([header, data])
            else:
                buffer = "".join([buffer, data])
        self.sendMessage(buffer)
    
    def reportNetwork(self):
        header = self.C.messageHeader("interface")
        net = psutil.net_io_counters(pernic=True)
        buffer = header
        for nic in net:
            name = str(nic)
            n = net[name]
            data = self.C.pack(TYPE_PLUGIN_INSTANCE, name)
            data = "".join([data, self.C.pack(TYPE_TYPE, "if_octets")])
            data = "".join([data, self.C.packValues([VALUE_COUNTER, n.bytes_recv], [VALUE_COUNTER, n.bytes_sent])])
            data = "".join([data, self.C.pack(TYPE_TYPE, "if_packets")])
            data = "".join([data, self.C.packValues([VALUE_COUNTER, n.packets_recv], [VALUE_COUNTER, n.packets_sent])])
            data = "".join([data, self.C.pack(TYPE_TYPE, "if_dropped")])
            data = "".join([data, self.C.packValues([VALUE_COUNTER, n.dropin], [VALUE_COUNTER, n.dropout])])
            data = "".join([data, self.C.pack(TYPE_TYPE, "if_errors")])
            data = "".join([data, self.C.packValues([VALUE_COUNTER, n.errin], [VALUE_COUNTER, n.errout])])
            if len(buffer) + len(data) > 1400:
                self.sendMessage(buffer)
                buffer = "".join([header, data])
            else:
                buffer = "".join([buffer, data])
        self.sendMessage(buffer)
     
    def reportDiskUsage(self):
        header = self.C.messageHeader("df")
        buffer = header
        partitions = psutil.disk_partitions()
        for p in partitions:
            if 'fixed' in p.opts:
                try:
                    useage = psutil.disk_usage(p.mountpoint)
                    name = re.sub(r'^/', '', p.mountpoint)
                    data = self.C.pack(TYPE_PLUGIN_INSTANCE, name)
                    data = "".join([data, self.C.pack(TYPE_TYPE, "percent_bytes")])
                    data = "".join([data, self.C.pack(TYPE_TYPE_INSTANCE, "free")])
                    data = "".join([data, self.C.packValues([VALUE_GAUGE, useage.percent])])
                    if len(buffer) + len(data) > 1400:
                        self.sendMessage(buffer)
                        buffer = "".join([header, data])
                    else:
                        buffer = "".join([buffer, data])
                except Exception as ex:
                    self.logger.logit("reportDiskUsage:disk_usage(%s): %s" % (p.mountpoint, str(excep)), level=LOG_ERROR)
        self.sendMessage(buffer)
    
    def reportDiskIO(self):
        header = self.C.messageHeader("disk")
        buffer = header
        io = psutil.disk_io_counters(perdisk=True)
        for diskname in io:
            d = io[diskname]
            data = self.C.pack(TYPE_PLUGIN_INSTANCE, diskname)
            data = "".join([data, self.C.pack(TYPE_TYPE, "disk_octets")])
            data = "".join([data, self.C.packValues([VALUE_COUNTER, d.read_bytes], [VALUE_COUNTER, d.write_bytes])])
            data = "".join([data, self.C.pack(TYPE_TYPE, "disk_ops")])
            data = "".join([data, self.C.packValues([VALUE_COUNTER, d.read_count], [VALUE_COUNTER, d.write_count])])
            if len(buffer) + len(data) > 1400:
                self.sendMessage(buffer)
                buffer = "".join([header, data])
            else:
                buffer = "".join([buffer, data])
        self.sendMessage(buffer)
            
    def reportMemory(self):
        #
        # This should all fit in one message...
        #
        header = self.C.messageHeader("memory")
        p = psutil.virtual_memory()
        buffer = "".join([header, self.C.pack(TYPE_TYPE, "memory")])
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "used")])
        buffer = "".join([buffer, self.C.packValues([VALUE_GAUGE, p.used])])
        #
        # buffers and cached do not seem to be present on windows...
        # ... but just in case they show up in future...
        try:
            i = p.buffers
            buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "buffers")])
            buffer = "".join([buffer, self.C.packValues([VALUE_GAUGE, i])])
        except:
            i = 0
        try:
            i = p.cached
            buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "cached")])
            buffer = "".join([buffer, self.C.packValues([VALUE_GAUGE, i])])
        except:
            i = 1
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "free")])
        buffer = "".join([buffer, self.C.packValues([VALUE_GAUGE, p.available])])
        s = psutil.swap_memory()
        buffer = "".join([buffer, self.C.pack(TYPE_PLUGIN, "swap")])
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE, "swap")])
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "used")])
        buffer = "".join([buffer, self.C.packValues([VALUE_GAUGE, s.used])])
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "free")])
        buffer = "".join([buffer, self.C.packValues([VALUE_GAUGE, s.free])])
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE, "swap_io")])
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "in")])
        buffer = "".join([buffer, self.C.packValues([VALUE_DERIVE, s.sin])])
        buffer = "".join([buffer, self.C.pack(TYPE_TYPE_INSTANCE, "out")])
        buffer = "".join([buffer, self.C.packValues([VALUE_DERIVE, s.sout])])
        self.sendMessage(buffer)
    
    def mainLine(self):
        self.reportCPU()
        self.reportNetwork()
        self.reportDiskUsage()
        self.reportMemory()
        self.reportDiskIO()

    def buildSocket(self, host, port = 25826):
        self.server = host
        self.portnum = port
        self.sendsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

class Agent:        
    keepRunning = False
    isAlive = False
    agent = None

    def __init__(self):
        self.agent = CollectdAgent()
        self.agent.buildSocket("192.168.1.1")
        self.agent.logger = Logging()
        self.agent.C = Collect()
        self.keepRunning = True

    def MainLoop(self):
        self.isAlive = True
        while self.keepRunning:
            walltime = int(time.time())
            try:
                self.agent.mainLine()
            except Exception:
                e = sys.exc_info()
                self.agent.logger.logit("Exception: %s" % (str(e[1])), level=Logging.LOG_ERROR)
                print "Exception: %s" % (str(e[1]))
                tb = e[2]
                traceback.print_tb(tb)
                break
    
            finished = int(time.time())
            runtime = finished - walltime
            if runtime < 0:
                runtime = -1 * runtime
            if runtime == 0:
                time.sleep(waittime)
            else:
                time.sleep(waittime - (runtime % waittime))
        self.isAlive = False
    
    def StopLoop(self):
        self.keepRunning = False
        while self.isAlive:
            time.sleep(1)
    
if __name__ == "__main__":
     running = Agent()
     running.MainLoop()
     
