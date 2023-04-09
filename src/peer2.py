import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import select
import util.simsocket as simsocket
import struct
import socket
import util.bt_utils as bt_utils
import hashlib
import argparse
import pickle
import time
import logging
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.DEBUG,  # 控制台打印的日志级别
                    # filename='./new.log',
                    # filemode='w',  ##模式，有w和a，w就是写模式，每次都会重新写日志，覆盖之前的日志
                    # # a是追加模式，默认如果不写的话，就是追加模式
                    format=
                    '%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s'
                    # 日志格式
                    )

BUF_SIZE = 1400
MAX_PAYLOAD = 1024
CHUNK_DATA_SIZE = 512 * 1024
HEADER_LEN = struct.calcsize("HBBHHII20s")
ex_output_file = None

# 每一个chunck 处理的进度
ex_received_chunk = dict()
# TODO crash 清空 (已经修复了)


BASIC_RTT = 150  # 这个暂时不默认的

# 当前还剩下多少chuck没有接收到  {index: chunkhash} #这个是不动的，达成目标就达成了
require_chunk = dict()

have_finish_chunk = dict()

# 从发送get请求开始就证明开启了一个连接，(排除peer突然宕机（时间超时自动取消该连接))
recv_table = dict()

# 发送方维护一个dict()  #向谁发送什么文件

send_table = dict()

receiver_time = 0
WAIT_TIME = 3


def process_download(sock, chunkfile, outputfile):
    '''
    if DOWNLOAD is used, the peer will keep getting files until it is done
    '''
    global ex_output_file
    global ex_received_chunk
    global require_chunk

    download_hash = bytes()
    ex_output_file = outputfile
    # Step 1: read chunkhash to be downloaded from chunkfile

    with open(chunkfile, 'r') as cf:
        for line in cf:
            _ = line.strip().split(" ")
            if (len(_) == 2):
                ex_received_chunk[_[1]] = bytes()  # 需要被处理的hash值
                require_chunk[_[1]] = _[0]

    send_Whohas(sock)


def get_leaving_task():
    leave_chunk = []
    for i in list(require_chunk.keys()):

        #                        已经完成了        +   正在传输的
        if i not in list(config.haschunks.keys()) + getZero():
            leave_chunk.append(i)
    return leave_chunk


# 保证了一对一(FIXME)
def get_relex_peer():
    port_list = [recv_table[i].from_addr[1] for i in getZero()]
    ex_self = [i for i in config.peers if i[0] != str(config.identity)]
    return [i for i in ex_self if i[2] not in port_list]


def send_Whohas(sock):
    global receiver_time
    leaving_chuncks = get_leaving_task()
    relexing_peers = get_relex_peer()
    # logging.debug("relexing_peers")
    # logging.debug(relexing_peers)

    if len(leaving_chuncks) != 0:
        # 只发一个包，包里面装有所有想要的东西
        download_hash = bytes()
        for index in leaving_chuncks:
            datahash = bytes.fromhex(index)  # hex_str to bytes
            download_hash += datahash
        whohas_header = struct.pack("!HBBHHII20s", 52305, 35, 0, HEADER_LEN, HEADER_LEN + len(download_hash), 0, 0,
                                    bytes(20))
        whohas_pkt = whohas_header + download_hash
        for p in relexing_peers:
            if int(p[0]) != config.identity:
                sock.sendto(whohas_pkt, (p[1], int(p[2])))

        receiver_time = time.time()


def is_time_out(sock):
    if time.time() - receiver_time > WAIT_TIME:
        send_Whohas(sock)


def process_inbound_udp(sock):
    # Receive pkt
    global config
    global ex_sending_chunkhash
    global require_chunk
    global recv_table
    global send_table

    # 接收包
    pkt, from_addr = sock.recvfrom(BUF_SIZE)
    Magic, Team, Type, hlen, plen, Seq, Ack, chunk_hash_bytes = struct.unpack("!HBBHHII20s", pkt[:HEADER_LEN])
    data = pkt[HEADER_LEN:]

    if Type == 0:  # received an WHOHAS pkt

        # receiver 需求什么?
        whohas_chunk_hash = data
        arrange_send_to = []
        for i in range(0, len(whohas_chunk_hash), 20):
            arrange_send_to.append(bytes.hex(whohas_chunk_hash[i:i + 20]))

        # 我有什么？
        i_have_chunckhash = bytes()
        for chunck_str in arrange_send_to:
            if chunck_str in config.haschunks.keys():
                i_have_chunckhash += bytes.fromhex(chunck_str)

        # 有就直接发送I Have
        if len(i_have_chunckhash) != 0:
            ihave_header = struct.pack("!HBBHHII20s",
                                       52305,
                                       35,
                                       1,
                                       HEADER_LEN,
                                       HEADER_LEN + len(i_have_chunckhash),
                                       0,
                                       0,
                                       bytes(20))
            ihave_pkt = ihave_header + i_have_chunckhash
            sock.sendto(ihave_pkt, from_addr)


    # receiver
    elif Type == 1:  # received an IHAVE pkt # send back GET pkt

        get_chunk_hash = data
        # 接收到I have 请求中 包含的那个节点拥有的元素
        it_have_chunk = set()
        for i in range(0, len(get_chunk_hash), 20):
            it_have_chunk.add(bytes.hex(get_chunk_hash[i:i + 20]))
        # 留意一下，目前是选取最后一个，可能会影响整体的传输（FIXME)
        candidate = set(require_chunk.keys()) - set(have_finish_chunk.keys()) - set(getZero())

        choose_chunk = None
        for ch in it_have_chunk:
            if ch in candidate:
                choose_chunk = ch

        if choose_chunk is not None:
            tosend_chunk_hash = bytes.fromhex(choose_chunk)
            get_header = struct.pack("!HBBHHII20s",
                                     52305,
                                     35,
                                     2,
                                     HEADER_LEN,
                                     HEADER_LEN + len(tosend_chunk_hash),
                                     0,
                                     0,
                                     bytes(20))
            get_pkt = get_header + tosend_chunk_hash

            if choose_chunk not in recv_table.keys():
                recv_table[choose_chunk] = RecvSession(sock, from_addr)
                sock.sendto(get_pkt, from_addr)
            elif recv_table[choose_chunk].tag == 2:

                recv_table[choose_chunk] = RecvSession(sock, from_addr)
                ex_received_chunk[choose_chunk] = bytes()
                sock.sendto(get_pkt, from_addr)

    # sender
    elif Type == 2:  # received a GET pkt
        sending_chunkhash = bytes.hex(data[:20])
        chunk_data = config.haschunks[sending_chunkhash][:MAX_PAYLOAD]

        # 建立一个连接 记住每次建立连接只会发送一个包, 因为cwnd = 1
        send_table[from_addr] = SendSession(from_addr, sock, sending_chunkhash)

        data_header = struct.pack("!HBBHHII20s",
                                  52305,
                                  35,
                                  3,
                                  HEADER_LEN,
                                  HEADER_LEN + len(chunk_data),
                                  1,
                                  0,
                                  bytes.fromhex(sending_chunkhash))

        sock.sendto(data_header + chunk_data, from_addr)

        send_table[from_addr].update_expect()
        send_table[from_addr].startTime()
        send_table[from_addr].startRtt()

    # receiver
    elif Type == 3:  # received a DATA pkt

        chunk_hash = bytes.hex(chunk_hash_bytes)
        recv_table[chunk_hash].startTime()

        if len(ex_received_chunk[chunk_hash]) == CHUNK_DATA_SIZE:
            config.haschunks[chunk_hash] = ex_received_chunk[chunk_hash]
            have_finish_chunk[chunk_hash] = ex_received_chunk[chunk_hash]
            recv_table[chunk_hash].tag = 1
            send_Whohas(sock)

            if len(have_finish_chunk) == len(require_chunk):
                with open(ex_output_file, "wb") as wf:
                    pickle.dump(ex_received_chunk, wf)

        else:
            if recv_table[chunk_hash].acc_seq + 1 == Seq:
                recv_table[chunk_hash].acc_seq = Seq
                ex_received_chunk[chunk_hash] += data

            ack_pkt = struct.pack("!HBBHHII20s",
                                  52305, 35,
                                  4,
                                  HEADER_LEN,
                                  HEADER_LEN,
                                  0,
                                  recv_table[chunk_hash].acc_seq,
                                  chunk_hash_bytes
                                  )

            sock.sendto(ack_pkt, from_addr)

    # sender
    elif Type == 4:
        ex_sending_chunkhash = bytes.hex(chunk_hash_bytes)
        current_send_session = send_table[from_addr]

        # received an ACK pkt
        ack_num = Ack
        # FIXME 这个地方是新增的,当遇到ack就应该更新时间了，否则如果只在重传的时候更新，当一次传播的太多了，就直接触发重了（好像也没问题）
        #send_table[from_addr].startTime()

        # [:finish*MAX_PAYLOAD] ok
        send_table[from_addr].finish = max(ack_num, current_send_session.finish)

        # 完成接收
        if (ack_num) * MAX_PAYLOAD >= CHUNK_DATA_SIZE:
            logging.debug(f"finished sending {ex_sending_chunkhash}")
            # debug
            print(send_table[from_addr].cwnd_window)

        else:
            # 计算RTT 确认重传超时的时间
            rtt = send_table[from_addr].computeRtt()
            send_table[from_addr].limit_time = 2 * rtt
            # TODO 需要用特殊算法进行计算

            # test_dupAck
            send_table[from_addr].test_dupAck(ack_num)

            cur_cwnd = current_send_session.cwnd
            finish = current_send_session.finish
            expect = current_send_session.expect
            # 正常发送:一个cwnd 都接收完了,然后再一起发送
            if finish == expect:
                # debug:
                send_table[from_addr].cwnd_window.append(send_table[from_addr].cwnd)
                # 进入congestion avoidance
                if send_table[from_addr].cwnd >= send_table[from_addr].ssthresh:
                    send_table[from_addr].isCA = True

                # 这个是发送cwnd（send window）内的所有东西
                for i in range(cur_cwnd):
                    new_ack_number = finish + i  # 这个地方可能有bug
                    left = (new_ack_number) * MAX_PAYLOAD
                    right = min((new_ack_number + 1) * MAX_PAYLOAD,
                                CHUNK_DATA_SIZE)  # 这个地方可能会越界吧或者发送空数据，不过这个地方问题不大 可以检测发完没有
                    next_data = config.haschunks[ex_sending_chunkhash][left: right]  # ex_sending_chunkhash 需要更改

                    data_header = struct.pack("!HBBHHII20s",
                                              52305,
                                              35,
                                              3,
                                              HEADER_LEN,
                                              HEADER_LEN + len(next_data),
                                              new_ack_number + 1,
                                              0,
                                              chunk_hash_bytes)

                    sock.sendto(data_header + next_data, from_addr)

                send_table[from_addr].update_expect()
                send_table[from_addr].startTime()
                send_table[from_addr].startRtt()



def getZero():
    return [i for i in recv_table.keys() if recv_table[i].tag == 0]


class RecvSession:
    def __init__(self, sock, from_addr):
        # 这个表示已经接收到了什么
        self.acc_seq = 0
        self.start_time = time.time()
        self.crash_time = 5
        self.sock = sock
        self.from_addr = from_addr
        self.tag = 0  # 0代表开始但是没有完成, 1 代表已经完成, 2代表crash了

    def startTime(self):
        self.start_time = time.time()

    # 处理crash操作
    def is_time_out(self):
        if time.time() - self.start_time > self.crash_time:
            self.tag = 2
            send_Whohas(self.sock)
            self.startTime()


# 什么时候终结没有想清楚 传递结束了就终结
class SendSession:
    def __init__(self, from_addr, sock, ex_sending_chunkhash, limit_time=3):
        self.from_addr = from_addr
        self.sock = sock
        self.ex_sending_chunkhash = ex_sending_chunkhash
        self.start_time = time.time()
        self.limit_time = limit_time
        self.cwnd = 1
        self.ssthresh = 64
        self.dupAck = dict()
        self.finish = 0
        self.expect = 0
        self.RRT = 0
        self.RRT_time = 0
        self.isCA = False
        self.temp = 0  # double
        self.cwnd_window = []

        ##################
        self.has_retransmited = False
        self.retransmit_time = time.time()
        self.delay_retransmit_time = 0.2
        ##################

        # 每一次sender 发送data 启动

    def startTime(self):
        self.start_time = time.time()

    # 每次发送之后，都要更新expect 相当于窗口的back
    def update_expect(self):
        self.expect = min(self.finish + self.cwnd, CHUNK_DATA_SIZE // MAX_PAYLOAD)

    def startRtt(self):
        self.RRT_time = time.time()

    def computeRtt(self):
        return time.time() - self.RRT_time

    # 每一次time_out 则进行重新传
    def is_time_out(self):
        if time.time() - self.start_time > self.limit_time:
            self.ReTransmit()

    ########
    def delay_retransmit(self):
        # 重传后一段时间仍未收到ack包则继续重传
        if time.time() - self.retransmit_time >= self.delay_retransmit_time:
            self.has_retransmited = False

    def start_retransmit(self):
        self.has_retransmited = True
        self.retransmit_time = time.time()

    def test_dupAck(self, ack_num):
        if ack_num in self.dupAck.keys():
            self.dupAck[ack_num] += 1
            if self.dupAck[ack_num] >= 3:
                # 还未重传则先重传并开始计时
                if not self.has_retransmited:
                    self.ReTransmit()
                    self.start_retransmit()
                self.delay_retransmit()
        else:
            # 重置重传标志
            self.has_retransmited = False
            self.dupAck.clear()
            self.dupAck[ack_num] = 1
            if not self.isCA:
                self.cwnd += 1
            else:
                self.temp += (1 / self.cwnd)
                if int(self.temp) == 1:
                    self.cwnd += 1
                    self.temp = 0

    def ReTransmit(self):
        if self.finish * MAX_PAYLOAD >= CHUNK_DATA_SIZE:
            pass
        else:
            for i in range(self.expect - self.finish):
                new_ack_number = self.finish + i  # 这个地方可能有bug

                left = new_ack_number * MAX_PAYLOAD
                right = min((new_ack_number + 1) * MAX_PAYLOAD,
                            CHUNK_DATA_SIZE)  # 这个地方可能会越界吧或者发送空数据，不过这个地方问题不大 可以检测发完没有
                next_data = config.haschunks[self.ex_sending_chunkhash][left: right]  # ex_sending_chunkhash 需要更改
                data_header = struct.pack("!HBBHHII20s",
                                          52305,
                                          35,
                                          3,
                                          HEADER_LEN,
                                          HEADER_LEN + len(next_data),
                                          new_ack_number + 1,
                                          0,
                                          bytes.fromhex(self.ex_sending_chunkhash))
                self.sock.sendto(data_header + next_data, self.from_addr)

            # 这个地方不能update_expect
            self.startTime()
            self.startRtt()
            self.ssthresh = max(2, self.cwnd // 2)
            self.cwnd = 1
            self.isCA = False


# 什么时候终结没有想清楚


def process_user_input(sock):
    command, chunkf, outf = input().split(' ')
    if command == 'DOWNLOAD':
        process_download(sock, chunkf, outf)
    else:
        pass


def peer_run(config):
    addr = (config.ip, config.port)
    sock = simsocket.SimSocket(config.identity, addr, verbose=config.verbose)

    try:
        while True:
            ready = select.select([sock, sys.stdin], [], [], 0.1)
            read_ready = ready[0]
            # is_time_out(sock)
            if len(read_ready) > 0:
                if sock in read_ready:
                    process_inbound_udp(sock)
                if sys.stdin in read_ready:
                    process_user_input(sock)
            if list(send_table.keys()) != 0:
                for s_S in send_table.keys():
                    send_table[s_S].is_time_out()

            if list(recv_table.keys()) != 0:
                for r_S in recv_table.keys():
                    recv_table[r_S].is_time_out()

            is_time_out(sock)

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == '__main__':
    """
    -p: Peer list file, it will be in the form "*.map" like nodes.map.
    -c: Chunkfile, a dictionary dumped by pickle. It will be loaded automatically in bt_utils. The loaded dictionary has the form: {chunkhash: chunkdata}
    -m: The max number of peer that you can send chunk to concurrently. If more peers ask you for chunks, you should reply "DENIED"
    -i: ID, it is the index in nodes.map
    -v: verbose level for printing logs to stdout, 0 for no verbose, 1 for WARNING level, 2 for INFO, 3 for DEBUG.
    -t: pre-defined timeout. If it is not set, you should estimate timeout via RTT. If it is set, you should not change this time out.
        The timeout will be set when running test scripts. PLEASE do not change timeout if it set.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', type=str, help='<peerfile>     The list of all peers', default='nodes.map')
    parser.add_argument('-c', type=str, help='<chunkfile>    Pickle dumped dictionary {chunkhash: chunkdata}')
    parser.add_argument('-m', type=int, help='<maxconn>      Max # of concurrent sending')
    parser.add_argument('-i', type=int, help='<identity>     Which peer # am I?')
    parser.add_argument('-v', type=int, help='verbose level', default=0)
    parser.add_argument('-t', type=int, help="pre-defined timeout", default=0)
    args = parser.parse_args()

    config = bt_utils.BtConfig(args)
    peer_run(config)

# %%
