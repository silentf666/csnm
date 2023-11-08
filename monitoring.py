#Todos:
# [] add count down on index to see when page is refreshing
# [] refresh page when server is added or edited
# [] url out of ip:port
# [] delte log when x days old or x size
# [] add every occuring change in status to a single file or better every server gets its own file
# [] buttons in the view to reduce size of the gui to see more
# [] status change in 24 hours, 7 days, 30 days...
# [] server monitoring | input fields in 1 row, info in the next row
 

import os
import time
import json
import threading
import shutil
import logging
import socket
import schedule
import concurrent.futures
import csv
from datetime import datetime
import matplotlib.pyplot as plt
import mpld3

from flask import Flask, render_template, request, redirect

app = Flask(__name__)

# Add logging configuration
logging.basicConfig(filename='logfile.log', level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S') 
#Backup config 
MAX_BACKUP_FILES = 10 #before every edit, a backup file is created. How many changes?
backup_folder = "config_backups"
backup_file_prefix = "server_config_backup"
#ping/check config
MAX_PING_RETRY = 2 # 3 retrys before going to offline or Warning
PING_RETRY_WAIT = 5 #amount of seconds before a retry takes place, if Ping is successfull within retry, STATUS = WARNING
checkIntervall = 20 #check stuff every X seconds
maximum_workers = 1 #how many workers for monitoring function, not sure this is working

socketTimeout = 1 #socket timeout for port checks

server_memory = []; #holds the data of the server status of all servers, before it gets written to the config file
config_update_intervall = 30 #transfer data from memory to server_config.txt every X seconds
server_log_folder = "server_logs" #where the log of each server (monitoring job) is stored

thread_lock = threading.Lock()
monitoring_queue_lock = threading.Lock()
monitoring_lock = threading.Lock()



#function to create "status memory" using server_config as the source information
# structure:
# server, last online, ping, telnet, 
def create_server_status_memory():
    global server_memory
    with thread_lock:
        server_memory = []
        status = []
        with open(config_file, 'r') as file:
            lines = file.readlines()
            for line in lines:
                server_info = line.strip().split(',')
                server_memory.append(server_info)
        print("server memory created", server_memory)
    
    
def update_server_memory(target_server, last_online, new_status, port_check,port):
    print("update_server_memory...")
    global server_memory
    with thread_lock:
        for server in server_memory: # server memory holds all servers and different status 
            if server[1] == target_server and server[5] == port: #if the loop reaches the server to update
                print("Update_server_memory...", server[1])
                if(port_check == True):
                    print("checkpoint 1")
                    server[3] = last_online
                    server[4] = new_status
                    server[6] = "Online"
                    server[5] = port
                elif(port_check == False and port != ""): #if the server entry has a port but is not open
                    print("checkpoint 2")
                    server[3] = last_online
                    server[4] = new_status
                    server[6] = "Offline"
                    server[5] = port
                elif(port_check == False and port == ""): #if no port is set for the server (means ping only)
                    print("checkpoint 3")
                    server[3] = last_online
                    server[4] = new_status
                    server[6] = ""
                    server[5] = ""
                elif(server[3] == "" and new_status == "offline"):
                    print("checkpoint 4")   #when no last online status is available and its still offline                        
                    server[4] = new_status
                else:
                    print("checkpoint 5")
                    server[4] = "unknown status"
                #print("_-----------MEMORY UPDATE----------_")
                #print(server[1])
                logging.info("Memory update done: %s", server[1])
                print("memory update done:")
                print(server_memory)

def view_update_server_memory(server_id, target_server, description, port):
    print("view_update_server_memory...")
    global server_memory
    with thread_lock:
        for server in server_memory: # server memory holds all servers and different status 
            if server[0] == server_id: #if the loop reaches the server to update            
                server[1] = target_server
                server[2] = description
                server[4] = ""
                server[5] = port
                server[6] = ""
                print("Updated the view information for server ID: ", server_id)
                logging.info("Updated the view information for server ID: %s", server_id)
    update_all_server_config()
                


# Function to ping the server
def ping_server(server_info):
    print('Pinging server:', server_info)   
    logging.info('Pinging server: %s', server_info)   
    response = os.system("ping -c 1 " + server_info)
    if response == 0:
        status = "Online"
        last_online = time.strftime('%Y-%m-%d %H:%M:%S')
        print("ping OK", status, last_online)
        return True, status, last_online
        
    else:
        for i in range(MAX_PING_RETRY):
            time.sleep(PING_RETRY_WAIT)
            print("Retry:",i,"for server:", server_info)
            logging.info("Retry: %d Server %s ", i, server_info)
            response = os.system("ping -c 1 " + server_info)
            if response == 0:
                logging.warning("Server %s has responded after retry", server_info)
                status = "Warning"
                last_online = time.strftime('%Y-%m-%d %H:%M:%S')
                return True, status, last_online
            else:
                status = "Offline"
                last_online = ""
                return False, status, last_online

    #update_server_memory(server_info, last_online, status, False, "") #False means, its not a port check but a ping check
    #print(server_memory) #todebug
    
# Function to check whether or not a port is open
def check_port(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(socketTimeout)
    try:
        sock.connect((host, port))
        print("host port is open")
        return True
    except socket.error:
        print("host port closed")
        return False
    finally:
        sock.close()

# Function to add a server and description to the configuration file
def add_server(server_id, server, description, port):
    global server_memory
    with thread_lock:
        server_info = [server_id, server, description, "", "", port, ""]
        server_memory.append(server_info)
        print("Added new server", server)
        create_server_log(server_id)
        logging.info("Added new server: %s", server)
        logging.info(server_memory)
        
def create_server_log(server_id):
    try:
        log_file = f"{server_id}_log.txt"
    except:
        print("Unable to create logfile for server %s", server_id)
        logging.error("Unable to create logfile for server %s", server_id)
        
        
    

# Function to remove a server from the configuration file
def remove_server(target_server):
    global server_memory
    with thread_lock:
        for server in server_memory:
            if server[0] == target_server:
                try:
                    server_memory.remove(server)
                    print("Removed Server", target_server)
                    logging.info("Removed Server: %s", target_server)
                except:
                    print("Error removing Server with ID:", target_server)
                    logging.error("Error removing server with ID: %s", target_server)
                    # write to config and reload page



def read_server_list():
    server_list = []
    with open(config_file, 'r') as file:
        for line in file:
            server_data = line.split(',')
            server_list.append(server_data)
    return server_list

#updating the server entries in the list, ip, description and port for example
'''def edit_server(server, new_value, config_file):
    create_config_backup(config_file)  # Create a backup before editing the configuration file
    print("EDIT SERVER FUNCTION ------------->");
    with open(config_file, 'r') as file:
        lines = file.readlines()
    with open(config_file, 'w') as file:
        for line in lines:
            server_info = line.strip().split(',')
            if server in server_info[0]:
                updated_info = [new_value if new_value else server_info[0]] + [info for info in server_info[1:]]
                file.write(','.join(updated_info) + '\n')
            else:
                file.write(line)
'''
# [] todo - should read data from server_memory and update this config file
def update_server_config(server_info, last_online, ping_status, port_status):
    with thread_lock:        
        print("updating server config:")
        print(server_info, last_online, status)
        
        with open("server_config.txt", "r") as file:
            lines = file.readlines()

        with open("server_config.txt", "w") as file:
            logging.info("Writing ping to server_config.txt")
            for line in lines:
                server_data = line.split(',')
                if server_info == server_data[1]:
                    logging.info("Matching %s with %s for ping update", server_info, server_data[1])
                    server_data[3] = last_online
                    server_data[4] = ping_status
                    file.write(','.join(server_data))
                else:
                    file.write(line)

        # File size logging
        file_size = os.path.getsize("server_config.txt")
        print("File Size: server_config", file_size)
        logging.info('File size after writing: %s bytes', file_size) 
        if file_size < 10:
            logging.error("!!! ERROR ??? !!!")
            logging.error('File size less than 10 bytes: %s bytes', file_size)

# takes all data stored in the server_memory and updates the server_config.txt            
def update_all_server_config():
    print("Update_all_server_config...") 
    global server_memory
    with thread_lock:        
        #print("updating ALL server config:")
        with open("server_config.txt", "w") as file:
            logging.info("Copy SERVER_MEMORY to server_config.txt")
            for server in server_memory:
                file.write(','.join(server)+'\n')

        # File size logging
        file_size = os.path.getsize("server_config.txt")
        print("File Size: server_config", file_size)
        logging.info('File size after writing: %s bytes', file_size) 
        if file_size < 10:
            logging.error("!!! ERROR ??? !!!")
            logging.error('File size less than 10 bytes: %s bytes', file_size)
    print("Update_all_server_config: calling: create_server_status_memory()")    
    create_server_status_memory()
    time.sleep(1)


def monitor_server_wrapper():
    with concurrent.futures.ThreadPoolExecutor(max_workers=maximum_workers) as executor:
        executor.submit(monitor_servers)

# Function to continuously monitor the servers
def monitor_servers():
    monitoring_queue = []
    with monitoring_lock:
        
        print("monitor_server...")
        while True:
            for server_info in server_memory:
                last_online = time.strftime('%Y-%m-%d %H:%M:%S')
                if server_info[1] not in monitoring_queue:
                    with monitoring_queue_lock:
                        monitoring_queue.append(server_info[1])
                    print("Queue:",monitoring_queue)
                    print("Monitoring Server:", server_info)
                    #logging.info("Monitoring Server: %s", server_info[1])
                    
                    if(server_info[5] != ""): #if there is a port set
                        print(server_info[1], "port open:", server_info[5])
                        port_result = check_port(server_info[1], int(server_info[5]))
                        print("port result:", port_result)
                        ping_results = ping_server(server_info[1])
                        print("ping results:", ping_results)
                                                
                        print("next step -> update memory")
                        #print("Port check done", port_results)
                        update_server_memory(server_info[1], ping_results[2], ping_results[1], port_result, server_info[5])
                        write_to_server_log(server_info[0], port_result)
                    elif(server_info[5] == ""):#there is no port defined, just check for ping
                        print("Checking stuff without ports", server_info[1])
                        ping_results = ping_server(server_info[1])
                        print("ping results:", ping_results)
                        print("next step -> update memory")
                        update_server_memory(server_info[1], ping_results[2], ping_results[1], False, "")
                        write_to_server_log(server_info[0], ping_results[0])
                    else:
                        print("Some unexpected monitoring behaviour with:", server_info[1])
                        logging.error("Some unexpected monitoring behaviour with: %s", server_info[1])
                        
                    print("Monitoring Done:", server_info[1])
                    print(monitoring_queue)
                    with monitoring_queue_lock:monitoring_queue.remove(server_info[1])  # Remove the server from the monitoring queue after checking
                else:
                    print("Server allready in QUEUE, skipping:", server_info[1])
                    logging.info("Server allready in QUEUE, skipping: %s", server_info[1])
                    continue


def generate_plot_html(server_id):
    print("_-------------------------------------------- PLOTTING DATA")
    # Example data
    x = [1, 2, 3, 4, 5]
    y = [2, 4, 6, 8, 10]

    # Create the plot
    fig, ax = plt.subplots()
    ax.plot(x, y, marker='o')

    # Convert the plot to HTML
    html_fig = mpld3.fig_to_html(fig)

    # Define the path for the HTML file
    file_path = os.path.join(server_log_folder, f"{server_id}_plot.html")

    # Save the HTML output to the specified server log folder
    with open(file_path, 'w') as f:
        f.write(html_fig)
    print("_-------------------------------------------- PLOTTING DATA END")
               
def write_to_server_log(server_id, data):   
    file_path = os.path.join(server_log_folder, server_id + "_log.txt")
    print("writing to server LOG FILE OF:", file_path)
    print(type(data))
    if(isinstance(data, bool)): #if the data is for a PORT check
        csv_data = [server_id, data, datetime.now()]
        try:
            with open(file_path, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(csv_data)
        except:
            print("problem writing to server log file")
    '''else: #if its a PING check
        csv_data = [server_id, data[0], datetime.now()]
        try:
            with open(file_path, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(csv_data)
        except:
            print("problem writing to server log file")'''
        
        

def config_scheduler():
    print("config_scheduler...")
    schedule.every(config_update_intervall).seconds.do(update_all_server_config)
    while True:
        schedule.run_pending()
        time.sleep(1)

def create_config_backup(config_file):
    if not os.path.exists(backup_folder):
        os.mkdir(backup_folder)

    backups = sorted(os.listdir(backup_folder))
    backups = [backup for backup in backups if backup.startswith(backup_file_prefix)]
    while len(backups) >= MAX_BACKUP_FILES:
        file_to_remove = os.path.join(backup_folder, backups.pop(0))
        os.remove(file_to_remove)

    if backups:
        last_backup = backups[-1]
        last_number = int(last_backup.split('_')[-1].split('.')[0])
        new_backup_name = f"{backup_file_prefix}_{last_number + 1}.txt"
    else:
        new_backup_name = f"{backup_file_prefix}_1.txt"

    backup_file = os.path.join(backup_folder, new_backup_name)
    shutil.copy2(config_file, backup_file)

@app.route('/')
def home():
    return render_template('index.html', server_list=read_server_list()) 
        
@app.route('/add', methods=['POST'])
def add():
    server = request.form['server']
    description = request.form['description']
    server_id = request.form['server_id']
    port = request.form.get('port')
    if not port:
        port = ""
    add_server(server_id, server, description, port)
    return redirect("/")

@app.route('/remove', methods=['GET'])
def remove():
    server = request.args.get('server')
    remove_server(server)
    return redirect("/")

@app.route('/edit', methods=['POST'])
def edit():
    data = json.loads(request.data)
    print("POST request DATA for server ID:", data['id'])
    print(data)
    view_update_server_memory(data['id'], data['server'], data['description'], data['port'])
    return redirect("/")



if __name__ == '__main__':
    config_file = "server_config.txt"
    create_server_status_memory()  
    
    # Start the monitoring process in a separate thread
    monitor_servers_thread = threading.Thread(target=monitor_server_wrapper)
    monitor_servers_thread.start()
    
    config_scheduler_thread = threading.Thread(target=config_scheduler)
    config_scheduler_thread.start()
    generate_plot_html(1)
    #monitor_servers()

    app.run(host='0.0.0.0', port=5000, debug=False)
