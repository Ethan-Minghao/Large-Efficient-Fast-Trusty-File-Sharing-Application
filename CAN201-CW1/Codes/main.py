import os
from socket import *
from os.path import join
import math
from threading import Thread
import time
import struct
import threading
import argparse
from Crypto.Cipher import DES
from binascii import b2a_hex, a2b_hex

def _argparse():
    parser = argparse.ArgumentParser(description = "This is just a test")
    # accept other peers' ip addresses
    parser.add_argument('--ip', action='store', required=True, dest='ip', help='peers ip')
    # switch on encryption function
    parser.add_argument('--encryption', action='store', required=False, default='no', dest='encryption', help='switch on encryption')
    return parser.parse_args()

# [Module] Used for encryption
class MyDESCrypt:
    # constructor
    def __init__(self, key = ''):
        if key is not '':
            self.key = key.encode('utf-8')
        else:
            self.key = '12345678'.encode('utf-8')
        self.mode = DES.MODE_CBC
    # encrypt function
    def encrypt(self,text):
        try:
            cryptor = DES.new(self.key, self.mode, self.key)
            length = 16
            count = len(text)
            if count < length:
                add = (length - count)
                text = text + ('\0' * add).encode('utf-8')
            elif count > length:
                add = (length - (count % length))
                text = text + ('\0' * add).encode('utf-8')
            self.ciphertext = cryptor.encrypt(text)
            return b2a_hex(self.ciphertext)
        except:
            return ""
    # decrypt function
    def decrypt(self, text):
        try:
            cryptor = DES.new(self.key, self.mode, self.key)
            plain_text = cryptor.decrypt(a2b_hex(text))
            return plain_text
        except:
            return ""

# --- ip and encryption mode identification ---
local_ip = ''  # ip address of this host
init = _argparse()
peers_ip = init.ip.split(',')  # other peers' ip addresses
encryption = init.encryption  # encryption mode (default is 'no')
# --- ports identification ---
receive_port = 20000  # TCP receive port (used for receiving file)
send_port = 30000  # UDP send port (used for broadcast and detect online)
udp_port = 25000 # UDP receive port (used for receiving message from other peers )
# --- declare UDP socket ---
udp_socket = socket(AF_INET, SOCK_DGRAM)
udp_socket.bind((local_ip, udp_port))
# --- declare some other necessary variables ---
file_dir = 'share'  # the folder for sharing files
sub_file_dir = file_dir  # the current directory
array = []  # the latest added files array
onlineDetector = {peers_ip[0] : 1,peers_ip[1] : 1 }  # symbol for online or not (1 means offline, 0 means online)
file_counter = 0  # count file in a folder
folder_event = threading.Event()  # lock to prevent directory changing before collecting all the files of a folder
send_event = threading.Event()  # lock to prevent sending 2 or more files at the same time
mtime_table = {}  # table for recording the up-to-date modified time of files
isSend = True  # lock to synchronize values in mtime_table when receiving files
# --- declare a encryptor ---
key = '19810317'  # key for decryption
des = MyDESCrypt(key)

# --- The following codes are mainly divided into 3 parts: [Thread], [Module] and [Function] ---
# --- the function marked as [Thread] will be a real thread in the running time ---
# --- the function marked as [Module] can perform some important functions such as send file and detect online ---
# --- rhe function marked as [Function] just performs some essential function ---

# [Thread: detect whether there's a newFile and judge the receiver]
def detectNewFile(ip_addr):
    global array, onlineDetector, mtime_table, isSend
    originalArray = os.listdir(file_dir)
    arrayLength = len(originalArray)
    #  initialize mtime table (folder omitted)
    for file in os.listdir(file_dir):
        if (not os.path.isdir(join(file_dir, file))):
            mtime_table[file] = os.stat(join(file_dir, file)).st_mtime
    print(mtime_table)
    #  detect whether there are some new files appearing in folder 'share'
    while True:
        array = os.listdir(file_dir)
        if (len(array) > arrayLength):  # new files appearing
            for fileName in originalArray:
                # the file received from other peers denoted with a prefix, say '1307'
                if (fileName.startswith('1307')):
                    try:
                        array.remove(fileName[4:])
                    except:
                        array.remove(fileName)
                else:
                    array.remove(fileName)
            newFile = array  # find out the new files
            originalArray.extend(newFile)
            arrayLength += len(newFile)
            print(newFile)
            for single_file in newFile:
                if (not single_file.startswith('1307')):  # if the file is added manually
                    if (not os.path.isdir(join(file_dir, single_file))):  # if the new file is not a folder
                        # modify mtime_table
                        mtime_table[single_file] = os.stat(join(file_dir, single_file)).st_mtime
                        print(mtime_table)
                    if (detectOnline(ip_addr) == 0):  # chocked until other peers reporting online
                        broadcast(single_file, ip_addr)  # start communication with another peer
                        send_event.wait()  # make communications in order
        # detect whether is any change in the file list
        for file in os.listdir(file_dir):
            # the file has already existed in mtime table (separate new files and modified files)
            if ( (not os.path.isdir(join(file_dir, file))) and (file in mtime_table.keys())):
                #  not in the process of receiving and value in mtime_table changed
                if (isSend and os.stat(join(file_dir, file)).st_mtime != mtime_table[file]):
                    if (detectOnline(ip_addr) == 0):
                        time.sleep(0.1)
                        updateFile(file, ip_addr, '')
                        mtime_table[file] = os.stat(join(file_dir, file)).st_mtime
                        print(mtime_table)
                        send_event.wait()

# [Thread: detect whether the killed machine is online and do the same thing]
def recover_thread(ip_addr, recover_file):
    if (detectOnline(ip_addr) == 0):
        broadcast(recover_file, ip_addr)
        send_event.wait()

# [Module: detect whether other machine is online]
def detectOnline(ip_addr):
    global onlineDetector
    while True:
        #  2 as a symbol sent to other peers to detect whether they are online
        udp_socket.sendto(struct.pack('!I', 2), (ip_addr, udp_port))
        time.sleep(1)
        if (onlineDetector[ip_addr] == 0):
            break
    onlineDetector[ip_addr] = 1  # reset the value for next time use
    return 0

# [Module: send file by TCP]
def sendFile(newFile, ip_addr, idString):
    file_name_length = len((idString + newFile).encode())
    print('start to send '+newFile  + ' to ' + ip_addr)
    sender = socket(AF_INET, SOCK_STREAM)
    sender.connect((ip_addr, receive_port))
    sender.send(struct.pack('!I', file_name_length) + (idString + newFile).encode())
    file_size = get_file_size(newFile)
    for i in range(50):
        sender.send(get_file_block(newFile, file_size, i))
    sender.close()

def updateFile(newFile, ip_addr, idString):
    f = open(join(sub_file_dir, newFile), 'rb')
    update_content = f.read(1024*1024)
    file_name_length = len((idString + newFile).encode())
    print('start to send ' + newFile + ' to ' + ip_addr)
    sender = socket(AF_INET, SOCK_STREAM)
    sender.connect((ip_addr, receive_port))
    sender.send(struct.pack('!I', file_name_length) + (idString + newFile).encode())
    sender.send(update_content)


# [Module: send file with encryption by TCP]
def sendEncFile(newFile, ip_addr, idString):
    file_name_length = len((idString + newFile).encode())
    print('start to send ' + newFile + ' to ' + ip_addr)
    f = open(join(sub_file_dir, newFile), 'rb')
    plain_text = f.read()
    f.close()
    encry_text = des.encrypt(plain_text)  # encrypt the content in file
    sender = socket(AF_INET, SOCK_STREAM)
    sender.connect((ip_addr, receive_port))
    sender.send(struct.pack('!I', file_name_length) + (idString + newFile).encode())
    sender.sendall(encry_text)
    sender.close()

# [Module: ask for other machine whether they have the 'newFile']
def broadcast(newFile, ip_addr):
    print('Broadcast' + newFile + ' to ' + ip_addr)
    if (os.path.isdir(join(file_dir, newFile))):
        # the second int 0 means it is folder
        udp_socket.sendto(struct.pack('!II', 1, 0)+newFile.encode(), (ip_addr, udp_port))
    else:
        # the second int 1 means not folder
        udp_socket.sendto(struct.pack('!II', 1, 1) + newFile.encode(), (ip_addr, udp_port))

# [Function: get file size]
def get_file_size(file_name):
    return os.path.getsize(join(sub_file_dir, file_name))

# [Function: get each file block for send]
def get_file_block(file_name, file_size, block_index):
    block_size = math.ceil(file_size/10)
    f = open(join(sub_file_dir, file_name), 'rb')
    f.seek(block_index * block_size)
    file_block = f.read(block_size)
    f.close()
    return file_block

# [Thread: answer for connection and receive file content]
def receive():
    global file_counter, mtime_table, isSend
    print('Receive start')
    receiver = socket(AF_INET, SOCK_STREAM)
    receiver.bind((local_ip, receive_port))
    receiver.listen(20)
    while True:
        text = b''
        conn, addr = receiver.accept()
        isSend = False  # set the value to be false to protect mtime_table when receive started
        file_length = struct.unpack('!I', conn.recv(4))[0]
        file_name = conn.recv(file_length).decode()
        print('set up')
        if (file_name in mtime_table):
            try:
                f = open(join(sub_file_dir, file_name), 'rb+')
            except:
                f = open(join(sub_file_dir, file_name), 'wb')
        else:
            f = open(join(sub_file_dir, file_name), 'wb') #maybe wait?
        time.sleep(0.1)
        while True:
            text = conn.recv(1024*64)
            f.write(text)
            if (text == b''):
                break
        f.close()
        # switch to encryption mode
        if (encryption == 'yes'):
            f = open(join(sub_file_dir, file_name), 'rb')
            encry_text = f.read()
            f.close()
            # decrypt the content and rewrite
            plain_text = des.decrypt(encry_text)
            f = open(join(sub_file_dir, file_name), 'wb')
            f.write(plain_text)
            f.close()
        # if it is just single file (not a file from a received folder) and not a existed file
        if (sub_file_dir == file_dir and (file_name not in mtime_table.keys())):
            os.rename(join(sub_file_dir, file_name), join(sub_file_dir, file_name[4:]))
            mtime_table[file_name[4:]] = os.stat(join(file_dir, file_name[4:])).st_mtime
        #  if the file already existed
        elif (sub_file_dir == file_dir):
            mtime_table[file_name] = os.stat(join(file_dir, file_name)).st_mtime
        isSend = True
        print(mtime_table)
        print(isSend)
        print('finished')
        file_counter += 1  # used for folder transmission (count the number of files in it)
        # if the number of files in folder up to 50, changing current directory is allowed
        if (file_counter >= 50):
            folder_event.set()

# [Thread: receive file Info and communication]
def udp_receive():
    while True:
        global array, newFile, file_name, sub_file_dir, file_dir, onlineDetector, file_counter, mtime_table
        msg, addr = udp_socket.recvfrom(1024)
        judgeCode = struct.unpack('!I', msg[:4])[0]
        print(judgeCode)
        if (judgeCode == 0):  # sending files if 0 received
            single_file = msg[4:].decode()
            if (os.path.isdir(join(file_dir, single_file))):  # if the newFile is a folder
                sub_file_dir = join(file_dir, single_file)  # enter the directory of new folder
                try:
                    for file in os.listdir(sub_file_dir): # can't apply broadcast
                        print(file)
                        sendFile(file, addr[0], '')
                    sub_file_dir = file_dir
                    time.sleep(0.5)
                    udp_socket.sendto(struct.pack('!I', 4), addr)
                    send_event.set()
                except Exception as e:
                    sub_file_dir = file_dir
                    print(addr[0] + ' has been killed')
                    print(e)
                    # start a new thread to detect whether the killed machine is online again
                    recovery = Thread(target = recover_thread, args=(addr[0], single_file))
                    recovery.start()
            else:  # if the newFile is a normal file
                try:
                    # if the encryption mode is started
                    if (encryption == 'yes'):
                        sendEncFile(single_file, addr[0], '1307')
                    else:
                        sendFile(single_file, addr[0], '1307')
                    send_event.set()
                except Exception as e:
                    print(addr[0] + ' has been killed')
                    print(e)
                    recovery = Thread(target=recover_thread, args=(addr[0], single_file))
                    recovery.start()

        elif (judgeCode == 1):  # receive file name
            folder_operation_code = struct.unpack('!I', msg[4:8])[0]  #
            file_name1 = msg[8:].decode()
            if (folder_operation_code == 0):  # 0 means it is folder
                if (('1307'+file_name1) not in os.listdir(file_dir)):
                    os.mkdir(join(file_dir, '1307' + file_name1))  # create new folder
                time.sleep(1)
                sub_file_dir = join(file_dir, '1307' + file_name1)  # prepare for write each file in new folder
            else:
                sub_file_dir = file_dir
            udp_socket.sendto(struct.pack('!I', 0) + file_name1.encode(), addr)

        elif (judgeCode == 2):  # send 3 to confirm online if 2 received
            udp_socket.sendto(struct.pack('!I', 3), addr)

        elif (judgeCode == 3):  # reset the value of onlineDetector when 3 received (peers online)
            onlineDetector[addr[0]] = 0

        elif (judgeCode == 4):  # the folder is received by peers
            folder_event.wait()
            file_counter = 0
            time.sleep(0.5)
            #  rename folder and jump out to normal share folder
            os.rename(sub_file_dir, join(file_dir, sub_file_dir.split('1307')[1]))
            sub_file_dir = file_dir
            for every_file in os.listdir(sub_file_dir):
                if (every_file.startswith('1307')):
                    os.rename(join(sub_file_dir, every_file), join(sub_file_dir, every_file[4:]))
                    mtime_table[every_file[4:]] = os.stat(join(file_dir, every_file[4:])).st_mtime


def createShare():
    if ('share' not in os.listdir()):
        os.mkdir('share')
        print('folder_share created!')

def main():
    createShare()
    receive_thread = Thread(target=receive)
    receive_thread.start()
    udp_thread = Thread(target=udp_receive)
    udp_thread.start()
    detect_send_thread1 = Thread(target=detectNewFile, args=(peers_ip[0],))
    detect_send_thread1.start()
    detect_send_thread2 = Thread(target=detectNewFile, args=(peers_ip[1],))
    detect_send_thread2.start()
    print(peers_ip)

if __name__ == '__main__':
    main()








