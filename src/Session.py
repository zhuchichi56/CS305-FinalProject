import time


class Session:

    #这个limit time可能是学出来的
    # def __init__(self,chunk_hash,from_addr,limit_time):
    # def __init__(self,chunk_hash,from_addr,limit_time):
    #     self.chunk_hash=chunk_hash
    #     self.from_addr=from_addr
    #     self.start_time = 0
    #     self.limit_time = limit_time
    #     self.cwnd = 1
    #     self.ssthresh = 64
    #     self.dupAck = 0
    #
    # #每一次sender 发送data 启动
    # def startTime(self):
    #     self.start_time = time.time()
    #
    # #每一次time_out 则进行重新传
    # def time_out(self):
    #     if(time.time()-self.start_time>self.limit_time):
    #         print("time out")

    def updown(self):
        for i in range(10):
            i+=1
            time.sleep(1)
        print(1)





class SendSession():
    def __init__(self,to_addr,limit_time=30):
        self.to_addr=to_addr
        self.start_time = 0
        self.limit_time = limit_time
        self.cwnd = 1
        self.ssthresh = 64
        self.dupAck = 0
        self.finish = 0
        self.expect= 0



    #每一次sender 发送data 启动
    def startTime(self):
        self.start_time = time.time()


    #每一次time_out 则进行重新传
    def is_time_out(self):
        if(time.time()-self.start_time>self.limit_time):
            print(self.limit_time)
            print("time out and reset the time")
            self.start_time = time.time()






