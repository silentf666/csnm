#Todos:
# [] add count down on index to see when page is refreshing
# [] refresh page when server is added or edited
# [] url out of ip:port
# [] delte log when x days old or x size
# [] add every occuring change in status to a single file or better every server gets its own file
# [] buttons in the view to reduce size of the gui to see more
# [] status change in 24 hours, 7 days, 30 days...
# [] server monitoring | input fields in 1 row, info in the next row
# [] counter for changed status on the index html
 

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
checkInterval = 60 #check stuff every X seconds
maximum_workers = 1 #how many workers for monitoring function, not sure this is working

socketTimeout = 1 #socket timeout for port checks

server_memory = []; #holds the data of the server status of all servers, before it gets written to the config file
config_update_intervall = 90 #transfer data from memory to server_config.txt every X seconds
server_log_foldername = "server_logs"
server_log_folder = "static/"+server_log_foldername #where the log of each server (monitoring job) is stored


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
        #print("server memory created", server_memory)
    
    
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
                #print(server_memory)

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


# [] todo - should read data from server_memory and update this config file
def update_server_config(server_info, last_online, ping_status, port_status):
    with thread_lock:        
        print("updating server config:")
        #print(server_info, last_online, status)
        
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
        #while True: was here.........
        print("monitor_server...")
        for server_info in server_memory:
            last_online = time.strftime('%Y-%m-%d %H:%M:%S')
            if server_info[1] not in monitoring_queue:
                with monitoring_queue_lock:
                    monitoring_queue.append(server_info[1])
                print("Monitoring Server:", server_info)
                logging.info("Monitoring Server: %s", server_info[1])
                
                if(server_info[5] != ""): #if there is a port set
                    port_result = check_port(server_info[1], int(server_info[5]))
                    ping_results = ping_server(server_info[1])
                    update_server_memory(server_info[1], ping_results[2], ping_results[1], port_result, server_info[5])
                    write_to_server_log(server_info[0], port_result)
                elif(server_info[5] == ""):#there is no port defined, just check for ping
                    ping_results = ping_server(server_info[1])
                    update_server_memory(server_info[1], ping_results[2], ping_results[1], False, "")
                    write_to_server_log(server_info[0], ping_results[0])
                else:
                    print("Some unexpected monitoring behaviour with:", server_info[1])
                    logging.error("Some unexpected monitoring behaviour with: %s", server_info[1])
        
                with monitoring_queue_lock:monitoring_queue.remove(server_info[1])  # Remove the server from the monitoring queue after checking
            else:
                print("Server allready in QUEUE, skipping:", server_info[1])
                logging.info("Server allready in QUEUE, skipping: %s", server_info[1])
                continue


def generate_plot_html(server_id):
    dates = set()
    print("Plotting data for Server ID:", server_id)
    logging.info("Plotting data for Server ID: %s", server_id)
    file_path = os.path.join(server_log_folder, f"{server_id}_log.txt")

                        
    x_values = []
    y_values = []

 
    with open(file_path, mode='r', newline='') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            date_str = row[2]  # Assuming the date is in the third column
            date_obj = datetime.strptime(date_str, "%d/%m %H:%M:%S")  # Convert the string to a datetime object
            x_values.append(date_obj)  # Append the datetime object to the list
            y_values.append(row[1])
            date = date_obj.date()  # Extract the date part only
            dates.add(date)
        num_days = len(dates)
        #print("Counted days:", num_days)
        #print("Values in x axis:", len(x_values))

    y_values_updated = [0 if val == 'True' else 1 for val in y_values]

    # Create the plot
    fig, ax = plt.subplots()
    ax.plot(x_values, y_values_updated, marker='o')
    
    # Set the y-axis lower limit to 0
    ax.set_ylim(bottom=0)

    plt.gcf().autofmt_xdate()
    plt.gca().xaxis.set_major_locator(plt.MaxNLocator(num_days))  # Set the number of x-axis ticks

    # Convert the plot to HTML
    html_fig = mpld3.fig_to_html(fig)

    # Define the path for the HTML file
    file_path = os.path.join(server_log_folder, f"{server_id}_plot.html")

    # Save the HTML output to the specified server log folder
    with open(file_path, 'w') as f:
        f.write(html_fig)
    print("Plotting DONE")
               
def write_to_server_log(server_id, data):   
    file_path = os.path.join(server_log_folder, f"{server_id}_log.txt")
    now = datetime.now()
    formatted_date = now.strftime("%d/%m %H:%M:%S")
    print("writing to server LOG FILE OF:", file_path)
    print(type(data))
    if(isinstance(data, bool)): #if the data is for a PORT check
        csv_data = [server_id, data, formatted_date]
        try:
            with open(file_path, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(csv_data)
        except:
            print("problem writing to server log file")

        
        

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
    
@app.route('/history')
def history():
    server_id = request.args.get('server')
    server_description = request.args.get('description')
    generate_plot_html(server_id)
    file_name = server_id + "_plot.html"
    return render_template('history.html', server_id=server_id, server_description = server_description, file_name = file_name, folder = server_log_foldername)
        
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
    threading.Timer(checkInterval, monitor_servers).start()
    
    config_scheduler_thread = threading.Thread(target=config_scheduler)
    config_scheduler_thread.start()

    app.run(host='0.0.0.0', port=5000, debug=False)
