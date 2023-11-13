#Todos:
# [] add count down on index to see when page is refreshing
# [x] refresh page when server is added or edited
# [x] url out of ip:port
# [x] !delete log when x days old
# [x] add every occuring change in status to a single file or better every server gets its own file
# [] buttons in the view to reduce size of the gui to see more
# [] notable status changes in 24 hours, 7 days, 30 days...
# [x] server monitoring | input fields in 1 row, info in the next row
# [] counter for changed status on the index html
# [x] garbage manager function -> deleting old or big log files. ok for now.
# [] scheduler function -> keeping an eye on the monitor_servers function
# [] Add a settings page to modify all the important variables
# [] <hr> line for each new day in status_list.html
# [x] directly update index view when server is added / edited
# [] "check now" button to trigger ping and port checks
# []  status list view: make each day "collapsable"?
# [] ping retry - rework needed so 0 would be no retry but its 1)
 

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
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import matplotlib.dates as mdates
import mpld3


from flask import Flask, render_template, request, redirect, send_from_directory

app = Flask(__name__)


logging.basicConfig(filename='logfile.log', level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', datefmt='%d-%m-%Y %H:%M:%S') 
thread_lock = threading.Lock()
monitoring_queue_lock = threading.Lock()
monitoring_lock = threading.Lock()
server_memory = []; #holds the data of the server status of all servers, before it gets written to the config file

###################################################### CONFIG SECTION ################################################################
###Backup config 
MAX_BACKUP_FILES = 10 #before every edit, a backup file is created. How many changes?
config_file = "server_config.txt" #should not be changed
backup_folder = "config_backups" #should not be changed
backup_file_prefix = "server_config_backup" #should not be changed
###ping/check config
MAX_PING_RETRY = 2 # 3 retrys before going to offline or Warning. Counting from 0,1,2... (rework needed so 0 would be no retry but its 1)
PING_RETRY_WAIT = 5 #amount of seconds before a retry takes place, if Ping is successfull within retry, STATUS = WARNING
checkInterval = 60 #check ping and ports every X seconds
###threading config
maximum_workers = 1 #how many workers for monitoring function, not sure this is working
###telnet/port config
socketTimeout = 1 #socket timeout for port checks


config_update_intervall = 90 #transfer data from memory to server_config.txt every X seconds
server_log_foldername = "server_logs"
server_log_folder = "static/"+server_log_foldername #where the log of each server (monitoring job) is stored
log_file_age_days = 30 #how many days you want to keep the log files before its automatically deleted
log_cleanup_interval_days = 1 # clean up the log every x days
######################################################## CONFIG SECTION END ############################################################





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

            
def check_server_config_file(config_file):
    try:
        with open(config_file, 'r') as file:
            print("config file exists")
    except:
        print("no config file")
        server_memory = [1, "localhost", "localhost","","","","","",]
        with open(config_file, 'w') as file:
            file.write(','.join(map(str, server_memory)))
            print("writing ...")
        print("New config file created.")
    

        
    
def update_server_memory(target_server, last_online, new_status, port_check,port):
    #print("update_server_memory...")
    global server_memory
    with thread_lock:
        for server in server_memory: # server memory holds all servers and different status 
            if server[1] == target_server and server[5] == port: #if the loop reaches the server to update
                print("Update_server_memory...", server[1])
                if(port_check == True):
                    server[3] = last_online
                    server[4] = new_status
                    server[6] = "Online"
                    server[5] = port
                elif(port_check == False and port != ""): #if the server entry has a port but is not open
                    server[3] = last_online
                    server[4] = new_status
                    server[6] = "Offline"
                    server[5] = port
                elif(port_check == False and port == ""): #if no port is set for the server (means ping only)
                    server[3] = last_online
                    server[4] = new_status
                    server[6] = ""
                    server[5] = ""
                elif(server[3] == "" and new_status == "offline"): #when no last online status is available and its still offline                        
                    server[4] = new_status
                else:
                    server[4] = "unknown status"
                logging.info("Memory update done: %s", server[1])

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
        last_online = time.strftime('%d-%m-%Y %H:%M:%S')
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
                last_online = time.strftime('%d-%m-%Y %H:%M:%S')
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
        create_config_backup()
       
        
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
    create_config_backup()

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
        for server_info in server_memory:
            last_online = time.strftime('%d-%m-%Y %H:%M:%S')
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
                logging.info("Server allready in QUEUE, skipping: %s", server_info[1])
                continue
        print("### all servers checked ###")
        logging.info("### all servers checked ###")
        threading.Timer(checkInterval, monitor_servers).start()


def generate_plot_html(server_id):
    day_color = 'green'
    dates = set()
    logging.info("Plotting data for Server ID: %s", server_id)
    file_path = os.path.join(server_log_folder, f"{server_id}_log.txt")

                        
    x_values = []
    y_values = []

 
    with open(file_path, mode='r', newline='') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            date_str = row[2]  # Assuming the date is in the third column
            date_obj = datetime.strptime(date_str, "%d/%m/%y %H:%M:%S")  # Convert the string to a datetime object
            x_values.append(date_obj)  # Append the datetime object to the list
            y_values.append(row[1])
            date = date_obj.date()  # Extract the date part only
            dates.add(date)
        num_days = len(dates)
        #print("Counted days:", num_days)
        #print("Values in x axis:", len(x_values))

    y_values_updated = [0 if val == 'True' else 1 for val in y_values]
    

    # Create the plot
    plt.figure(figsize=(15,6))
    fig, ax = plt.subplots(figsize=(15,6))
    ax.plot(x_values, y_values_updated, marker='o')
    
    # Set the y-axis lower limit to 0
    ax.set_ylim(bottom=0)
    
    # Set y-axis ticks and labels
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Online", "Offline"])
    
    plt.gcf().autofmt_xdate()
    plt.gca().xaxis.set_major_locator(plt.MaxNLocator(num_days))  # Set the number of x-axis ticks
    fig.canvas.draw()
    file_path = os.path.join(server_log_folder, f"{server_id}_plot.svg")
    fig.savefig(file_path)
    mpld3.save_html(fig, os.path.join(server_log_folder, f"{server_id}_plot.html"))
    
def generate_full_status_list(server_id):
    print("generating full status list for server:", server_id)
    try:
        file_path = os.path.join(server_log_folder, f"{server_id}_log.txt")
    except:
        print("problem with filepath")
    
    def get_status(status):
        if status == "False":
            return "offline"
        elif status == "True":
            return "online"
        elif status == "warning":
            return "warning"
        else:
            return ""

    with open(file_path, mode='r', newline='') as file:
        csv_reader = csv.reader(file)
        
        # Prepare data for rendering
        data = []
        for row in csv_reader:
            # Use a list to store row data
            row_data = []
            
            # Access elements by index and convert if needed
            date = row[2]
            status = get_status(row[1])
            
            # Append elements to the row_data list
            row_data.append(date)
            row_data.append(status)
            
            # Append the row_data list to the data list
            data.append(row_data)
    return data

               
def write_to_server_log(server_id, data):   
    file_path = os.path.join(server_log_folder, f"{server_id}_log.txt")
    now = datetime.now()
    formatted_date = now.strftime("%d/%m/%y %H:%M:%S")
    print("writing to server LOG FILE OF:", file_path)
    if(isinstance(data, bool)): #if the data is for a PORT check
        csv_data = [server_id, data, formatted_date]
        try:
            with open(file_path, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(csv_data)
        except:
            print("problem writing to server log file")
            
def log_cleanup():
    check_and_delete_log_files() #delete logs from server ids not in the server_config anymore
    def parse_date(date_str):
        return datetime.strptime(date_str.strip(), "%d/%m/%y %H:%M:%S")
    
    def delete_old_entries(file_path):
        print("Logfile cleanup:", file_path)
        logging.info("Logfile cleanup %s", file_path)
    # Calculate the date 30 days ago
        days_ago = datetime.now() - timedelta(days=log_file_age_days)

        # Read all lines from the file
        with open(file_path, 'r') as file:
            lines = file.readlines()

        # Filter lines to keep only those not older than 30 days
        filtered_lines = [line for line in lines if parse_date(line.split(',')[2]) >= days_ago]

        # Write the filtered lines back to the file
        with open(file_path, 'w') as file:
            file.writelines(filtered_lines)
        print("Logfiles cleanup done...")
        logging.info("Logfiles cleanup done...")
    
    #first get all the server ids, then loop through the files and 
    server_ids = get_server_ids()
    for server_id in server_ids:
        file_path = os.path.join(server_log_folder, f"{server_id}_log.txt")
        if os.path.exists(file_path):
            delete_old_entries(file_path)
        else:
            logging.error("Old log exist, which should not %s", file_path) 
    
    

def get_server_ids(): #get all the server IDs from the backup_logs files
    server_ids = []

    # Loop through all files in the folder
    for filename in os.listdir(server_log_folder):
        # Check if the file is a .txt file
        if filename.endswith('.txt'):
            # Extract the server ID from the filename
            server_id = filename.split('_')[0]

            # Add the server ID to the list if it's not already present
            if server_id not in server_ids:
                server_ids.append(server_id)

    return server_ids

#deletes all log files of servers which are not in the server_config anymore
#gets called when the log_cleanup function is called
def check_and_delete_log_files(): 
    # Get the list of server IDs from log files
    log_server_ids = get_server_ids()

    # Read the server IDs from the server_config.txt file
    with open('server_config.txt', 'r') as config_file:
        config_lines = config_file.readlines()

    # Extract server IDs from the server_config.txt file
    config_server_ids = [line.split(',')[0] for line in config_lines]

    # Identify the log files to delete
    files_to_delete = [f"{server_id}_log.txt" for server_id in log_server_ids if server_id not in config_server_ids]

    # Delete the identified log files
    for file_to_delete in files_to_delete:
        print("Logfile deleted:", file_to_delete)
        logging.info("Logfile deleted: %s", file_to_delete)
        file_path = os.path.join(server_log_folder, file_to_delete)
        os.remove(file_path)
        print(f"Deleted log file: {file_path}")

            

def config_scheduler():
    print("config_scheduler...")
    schedule.every(config_update_intervall).seconds.do(update_all_server_config)
    while True:
        schedule.run_pending()
        time.sleep(1)

def log_garbage_manager():
    print("checking for old logs to delete")
    schedule.every(log_cleanup_interval_days).day.at("00:00").do(log_cleanup)
    while True:
        schedule.run_pending()
        time.sleep(1)

def create_config_backup():
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
    print("config backup created")

@app.route('/')
def home():
    return render_template('index.html', server_list=read_server_list()) 
    
@app.route('/history')
def history():
    server_id = request.args.get('server')
    server_description = request.args.get('description')
    generate_plot_html(server_id)
    file_name = server_id + "_plot.svg"
    file_name_html = server_id + "_plot.html"
    return render_template('history.html', server_id=server_id, server_description = server_description, file_name = file_name, folder = server_log_foldername, file_name_html = file_name_html)
    
    
@app.route('/history_status_list')
def history_status_list():
    server_id = request.args.get('server')
    server_description = request.args.get('description')
    full_status_list = generate_full_status_list(server_id)
    return render_template('status_list.html', server_id=server_id, server_description = server_description, data = full_status_list )
        
@app.route('/add', methods=['POST'])
def add():
    server = request.form['server']
    description = request.form['description']
    server_id = request.form['server_id']
    port = request.form.get('port')
    if not port:
        port = ""
    add_server(server_id, server, description, port)
    update_all_server_config()
    return redirect("/")

@app.route('/remove', methods=['GET'])
def remove():
    server = request.args.get('server')
    remove_server(server)
    update_all_server_config()
    return redirect("/")

@app.route('/edit', methods=['POST'])
def edit():
    data = json.loads(request.data)
    view_update_server_memory(data['id'], data['server'], data['description'], data['port'])
    create_config_backup()
    return redirect("/")

@app.route('/static/server_logs/<path:filename>')
def custom_static(filename):
    response = send_from_directory('static/server_logs', filename)

    # Set cache headers to prevent caching
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


if __name__ == '__main__':
    check_server_config_file(config_file)
    #config_file = "server_config.txt"
    create_server_status_memory()  
    
    # Start the monitoring process in a separate thread
    monitor_servers_thread = threading.Thread(target=monitor_server_wrapper)
    threading.Timer(checkInterval, monitor_servers).start()
    
    config_scheduler_thread = threading.Thread(target=config_scheduler)
    config_scheduler_thread.start()
    
    log_garbage_manager_thread = threading.Thread(target=log_garbage_manager)
    log_garbage_manager_thread.start()

    app.run(host='0.0.0.0', port=5000, debug=False)
