#!/usr/bin/env python
#
# A Poor's Man Profiler for java applications
#
# GPLv3 (c) Babel srl
#
# Author: Roberto Polli <rpolli@babel.it>
#
from nose import main as testmain
from nose import SkipTest
import re
import sys
import getopt
import time
from subprocess import Popen, PIPE
from StringIO import StringIO

verbose = False


def dprint(s):
    global verbose
    if verbose:
        print >>sys.stderr, s


class JStack(object):

    # jstack states, see http://docs.oracle.com/javase/1.5.0/docs/api/java/lang/Thread.State.html
    STATES = ('NEW', 'BLOCKED', 'TERMINATED', 'RUNNABLE', 'WAITING',
              'TIMED_WAITING')

    class AlreadyParsedError(Exception):
        pass

    def __init__(self, s_stack):
        """initialize jstack with the output of jstack command"""
        self.output = s_stack
        self.threads = []
        self.state_tot = dict(zip(JStack.STATES, [0 for x in JStack.STATES]))
        self.parsed = False

        # finally parse
        self.parse()

    def parse(self):
        """Parse jstack command output.

            Infos are gathered into a jstack object that handles some stats
        """
        if self.parsed:
            raise JStack.AlreadyParsedError

        class en_thread(object):
            pass

        # regular expressions for parsing
        sre_class = r'[A-z][A-z0-9.]+[A-z]'
        re_thread = re.compile(r'^"([^\"]+)"\s+(daemon )?prio=([0-9]+) tid=(0x[0-9a-f]+) nid=0x[0-9a-f]+ (in [^ ]+|runnable)')
        (en_thread.SOCK, en_thread.DAEMON, en_thread.PRIO,
         en_thread.TID, en_thread.WCHAN) = range(1, 6)
        re_trace = re.compile(r'^\s+at (' + sre_class + ')\(([^ ]+)\)')
        re_trace = re.compile(r'^\s+at (.+)$')
        re_state = re.compile(r'^\s+java.lang.Thread.State: ([^ ]+)')

        # to enable testing, I need to parse
        #    even a single string
        reader = self.output
        if isinstance(self.output, str):
            reader = self.output.splitlines()

        # trace    points to a dict() inside the current java thread
        #    and is used to store the backtrace of the current thread
        thread = None
        for line in reader:
            line = line.rstrip()
            dprint("line: [%s]" % line)
            m_thread = re_thread.match(line)
            m_trace = re_trace.match(line)
            m_state = re_state.match(line)

            if m_thread:
                """initialize a threa variable"""
                dprint("\t thread:[%s]" % m_thread.group(en_thread.SOCK))
                thread = {'sock': m_thread.group(en_thread.SOCK),
                          'id': m_thread.group(en_thread.TID),
                          'daemon': m_thread.group(en_thread.DAEMON),
                          'wchan': m_thread.group(en_thread.WCHAN).strip().replace("in ", ""),
                          'trace': dict(),
                          'state': None}
                self.threads.append(thread)

            elif thread and m_state:
                dprint("\t state: %s" % m_state.group(1))
                state = m_state.group(1)
                thread['state'] = state
                self.state_tot[state] += 1
                dprint("\t state_tot[%s]: %d" % (state, self.state_tot[state]))

            elif thread and m_trace:
                """update trace until it points to another thread"""
                assert thread['trace'] is not None
                dprint("\t trace: [%s]" % m_trace.group(1))
                thread['trace'].setdefault(m_trace.group(1), 0)
                thread['trace'][m_trace.group(1)] += 1
                dprint("trace %s" % thread['trace'])

        dprint("threads: %s" % self.threads)
        self.parsed = True

    def wchan(self):
        """ reverse map of wait channel and threads.

            eg. {
            methodA: [thread1,.., threadN], # thread blocked on methodA
                }
        """
        chans = dict()
        for x in self.threads:
            wc = x['wchan']
            chans.setdefault(wc, [])
            chans[wc].append(x['sock'])

        dprint("wchan: %s" % chans)
        return chans

    def joint(self, state=None, sock=None):
        """ print_summary of all methods count.

            eg. {
            methodA: 123,
            methodB: 35,
                }
        """
        dprint("joint. state: %s, sock: %s" % (state, sock))

        assert self.threads
        if state:
            assert state in JStack.STATES

        traces = dict()
        for t in self.threads:
            # eventually filter by state
            if state and t['state'] != state:
                continue
            if sock and (t['sock'].find(sock) == -1):
                continue
            else:
                dprint("joint: checking sock: %s" % t['sock'])

            for (c, v) in t['trace'].iteritems():
                traces.setdefault(c, 0)
                traces[c] += v

        return traces

    def print_summary(self, limit=0, threshold=0):
        print "Total threads: %d\n" % len(self.threads)
        for s in self.state_tot.iteritems():
            print "\tstate: %-15s %10d" % s

        for (chan, threads) in self.wchan().iteritems():
            print "\twchan: %s for %d threads" % (chan, len(threads))

        trace_count = self.joint()
        dprint("\ntrace_count: %s" % trace_count)
        JStack.print_summary_trace(
            trace_count, limit=limit, threshold=threshold)

    def csv(self):
        print "%5d " % len(self.threads),
        for s in JStack.STATES:
            print "%5d " % self.state_tot[s],

    @staticmethod
    def print_summary_trace(trace_count, limit=0, threshold=0):
        """Prints the trace counter, that should be a list of vectors"""
        assert isinstance(trace_count, dict) == True
        print "Most frequent calls (limit: %d, threshold: %s):" % (
            limit, threshold)
        if limit == 0:
            limit -= 1
        dprint("\ntrace_count: %s" % trace_count)
        for tc in sorted(trace_count.iteritems(), key=lambda x: x[1], reverse=True):
            if limit == 0:
                break
            if tc[1] < threshold:
                break

            print "\t%-120s %5d" % tc
            limit -= 1

    @staticmethod
    def sum(tot, stack_new, state=None, sock=None):
        """Return a dictionary with thread counters."""
        dprint("Summing jstats: state:%s,sock:%s" % (state, sock))
        threads_tot = dict()
        thread_union = [x for x in tot.iteritems()]
        thread_union.extend(
            [x for x in stack_new.joint(state=state, sock=sock).iteritems()])
        dprint("thread_union: %s" % thread_union)
        for (k, v) in thread_union:
            dprint("k: %s" % k)
            threads_tot.setdefault(k, 0)
            threads_tot[k] += v
        return threads_tot


class TestJStack(object):
    global verbose
    stack = None
    s_jstack_out = """
"Attach Listener" daemon prio=10 tid=0x51a6b000 nid=0x118e runnable [0x00000000]
    java.lang.Thread.State: RUNNABLE

    Locked ownable synchronizers:
                - None

"http-0.0.0.0-8080-6" daemon prio=10 tid=0x0bab5c00 nid=0xd73 in Object.wait() [0x4e5f5000]
    java.lang.Thread.State: WAITING (on object monitor)
                at java.lang.Object.wait(Native Method)
                at java.lang.Object.wait(Object.java:485)
                at org.apache.tomcat.util.net.JIoEndpoint$Worker.await(JIoEndpoint.java:415)
                - locked <0x67648fe8> (a org.apache.tomcat.util.net.JIoEndpoint$Worker)
                at org.apache.tomcat.util.net.JIoEndpoint$Worker.run(JIoEndpoint.java:441)
                at java.lang.Thread.run(Thread.java:662)

    Locked ownable synchronizers:
                - None

"http-0.0.0.0-8080-5" daemon prio=10 tid=0x0a82d000 nid=0xd72 in Object.wait() [0x4e646000]
    java.lang.Thread.State: WAITING (on object monitor)
                at java.lang.Object.wait(Native Method)
                at java.lang.Object.wait(Object.java:485)
                at org.apache.tomcat.util.net.JIoEndpoint$Worker.await(JIoEndpoint.java:415)
                - locked <0x6764b158> (a org.apache.tomcat.util.net.JIoEndpoint$Worker)
                at org.apache.tomcat.util.net.JIoEndpoint$Worker.run(JIoEndpoint.java:441)
                at java.lang.Thread.run(Thread.java:662)

    Locked ownable synchronizers:
                - None

"http-0.0.0.0-8080-4" daemon prio=10 tid=0x0a82bc00 nid=0xd71 in Object.wait() [0x4e697000]
    java.lang.Thread.State: WAITING (on object monitor)
                at java.lang.Object.wait(Native Method)
                at java.lang.Object.wait(Object.java:485)
                at org.apache.tomcat.util.net.JIoEndpoint$Worker.await(JIoEndpoint.java:415)
                - locked <0x6764d2c8> (a org.apache.tomcat.util.net.JIoEndpoint$Worker)
                at org.apache.tomcat.util.net.JIoEndpoint$Worker.run(JIoEndpoint.java:441)
                at java.lang.Thread.run(Thread.java:662)

    Locked ownable synchronizers:
                - None

"JBoss System Threads(1)-1" daemon prio=10 tid=0x09a28400 nid=0x7ec runnable [0x521ad000]
     java.lang.Thread.State: RUNNABLE
                at java.net.PlainSocketImpl.socketAccept(Native Method)
                at java.net.PlainSocketImpl.accept(PlainSocketImpl.java:390)
                - locked <0x6397c1e0> (a java.net.SocksSocketImpl)
                at java.net.ServerSocket.implAccept(ServerSocket.java:462)
                at java.net.ServerSocket.accept(ServerSocket.java:430)
                at org.jboss.web.WebServer.run(WebServer.java:320)
                at org.jboss.util.threadpool.RunnableTaskWrapper.run(RunnableTaskWrapper.java:148)
                at EDU.oswego.cs.dl.util.concurrent.PooledExecutor$Worker.run(PooledExecutor.java:756)
                at java.lang.Thread.run(Thread.java:662)

     Locked ownable synchronizers:
                - None


"""

    def setUp(self):
        self.stack = JStack(self.s_jstack_out)

    def test_sock(self):
        j_threads = self.stack.threads
        thread_sockets = [x['sock'] for x in j_threads]
        assert len(j_threads) == 5

        expected = ['Attach Listener', "JBoss System Threads(1)-1"]
        expected.extend(["http-0.0.0.0-8080-%d" % i for i in [4, 5, 6]])
        for sock in expected:
            assert sock in thread_sockets, "Expecting %s in %s" % (
                sock, thread_sockets)

    def test_wchan(self):
        j_wchan = self.stack.wchan()
        assert 'Object.wait()' in j_wchan
        expected = ["http-0.0.0.0-8080-%d" % i for i in [4, 5, 6]]
        for sock in expected:
            assert sock in j_wchan['Object.wait()']

    def test_state(self):
        j_state = self.stack.state_tot
        assert 'RUNNABLE' in j_state
        assert 'WAITING' in j_state
        assert j_state['RUNNABLE'] == 2
        assert j_state[
            'WAITING'] == 3, "expected: 3, had %d" % j_state['WAITING']

    def test_joint(self):
        t = self.stack.joint()
        assert t
        assert 'java.lang.Object.wait(Native Method)' in t
        assert t['java.lang.Object.wait(Native Method)'] == 3

    def test_joint(self):
        traces = self.stack.joint()
        assert traces
        assert 'java.lang.Object.wait(Native Method)' in traces
        assert traces['java.lang.Object.wait(Native Method)'] == 3

    def test_joint_sock_1(self):
        traces = self.stack.joint(sock="pluto")
        assert not traces

    def test_joint_sock_2(self):
        expected_stacktrace_size = 5
        t_2 = self.stack.joint(sock="http")
        assert len(t_2) == expected_stacktrace_size, "Expecting %d, was %d" % (
            expected_stacktrace_size, len(t_2))

    def test_summary(self):
        self.stack.print_summary()

    def test_sum(self):
        threads_first = JStack.sum(dict(), self.stack)
        threads_tot = JStack.sum(threads_first, self.stack)
        assert threads_tot
        for (k, v) in threads_tot.iteritems():
            dprint("threads_tot: k: %s,%s" % (k, v))
            assert v % 2 == 0
        JStack.print_summary_trace(threads_tot, 0, 0)

    def test_sum_sock_1(self):
        threads_first = JStack.sum(dict(), self.stack, sock="badname")
        assert not threads_first

    def test_sum_sock_2(self):
        threads_first = JStack.sum(dict(), self.stack, sock="http")
        threads_tot = JStack.sum(threads_first, self.stack, sock="http")
        assert threads_first
        assert len(threads_first) == len(threads_tot)

    def test_sum_sock_2(self):
        threads_first = JStack.sum(dict(), self.stack, sock="http")
        threads_tot = JStack.sum(threads_first, self.stack, sock=None)
        assert threads_first
        assert len(threads_first) < len(threads_tot)


#
# The Program
#
def usage():
    print "usage: jstack [-l limit] [-t threshold] [-j java_pid] [-s state] [-v] [-h]"
    print ""
    print "\t parse jstack output giving some statistics"
    print "\t number of threads, thread waiting and running"
    print "\t waiting channels"
    print "\t -s state of the process to filter: %s" % [
        x for x in JStack.STATES]
    print "\t -j pid of the jvm to trace"
    print "\t -i interval in seconds between each check"
    print "\t -l number of methods to report"
    print "\t -n thread name"

    exit(2)


def main():
    global verbose
    print "running main"

    (argc, argv) = (len(sys.argv), sys.argv)
    (limit, threshold, interval, state, jid, sock) = (0, 0, 0, None,
                                                      None, None)
    try:
            opts, args = getopt.getopt(argv[1:], "hvi:j:l:n:s:t:", ["help"])
    except getopt.GetoptError, err:
            # print help information and exit:
            print str(
                err)  # will print something like "option -a not recognized"
            usage()
            sys.exit(2)
    for o, a in opts:
        if o == "-v":
                verbose = True
        elif o in ("-h", "--help"):
                usage()
        elif o in ("-l"):
                limit = int(a)
        elif o in ("-t"):
                threshold = int(a)
        elif o in ("-i"):
                interval = a
        elif o in ("-j"):
                jid = a
        elif o in ("-s"):
                state = a
        elif o in ("-n"):
                sock = a
        else:
                assert False, "unhandled option"

    assert jid, usage()

    tot = dict()

    while True:
        p = Popen(["jstack", "-l", jid], stdout=PIPE, stderr=PIPE)
        s_jstack_out, stderr = p.communicate()
        jstack = JStack(s_jstack_out)

        if not interval:
            jstack.print_summary(limit=limit, threshold=threshold)
            break

        tot = JStack.sum(tot, jstack, state, sock)
        JStack.print_summary_trace(tot, limit=limit, threshold=threshold)

        time.sleep(1)

if __name__ == '__main__':
    exit(main())
