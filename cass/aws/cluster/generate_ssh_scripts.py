import boto3
import yaml
import os
import glob
import re

def generate_monitor_url_script(ip):
    base_path = "../.."
    script_name = "monitor.sh"

    template_file_path = f"{base_path}/{script_name}.tp"
    output_file_path = f"{base_path}/{script_name}"

    # Read the template file
    with open(template_file_path, 'r') as file:
        filedata = file.read()

    # Replace the placeholder with the actual IP or URL to the Monitor http service at the port 3000
    filedata = filedata.replace('<url>', f"http://{ip}:3000")

    # Write the modified content to the output file
    with open(output_file_path, 'w') as file:
        file.write(filedata)

    # Optionally, make the output script executable
    os.chmod(output_file_path, 0o750)

    print(f"Generated script: ./{script_name}")

def generate_run_script(nodes_data):
    base_path = "../.."
    script_name = "ssh_scripts/run"
    with open(f"{base_path}/{script_name}", 'w') as f:
        f.write("#!/bin/bash\n\n")
        f.write('arg1=$1\n')
        f.write('shift\n')  # Shift to move all arguments one position left
        f.write('arg2="${@:1}"\n\n')  # Capture all remaining arguments as a single string
                
        # Ensure loader nodes exist
        loader_nodes = [node for node in nodes_data if node["type"] == "Loader"]
        if loader_nodes:
            f.write('if [ "$arg1" == "loader" ]; then\n')
            for node in loader_nodes:
                ip = node["ip"]
                f.write(f'  echo "ssh ubuntu@{ip} >>"\n')
                f.write(f'  ssh -o StrictHostKeyChecking=no ubuntu@{ip} "$arg2"\n')
                f.write(f'  echo ""\n')                
            f.write("fi\n\n")
        
        # Ensure Scylla nodes exist
        scylla_nodes = [node for node in nodes_data if node["type"] == "Scylla"]
        if scylla_nodes:
            f.write('if [ "$arg1" == "scylla" ]; then\n')
            for node in scylla_nodes:
                ip = node["ip"]
                f.write(f'  echo "ssh ubuntu@{ip} >>"\n')
                f.write(f'  ssh -o StrictHostKeyChecking=no ubuntu@{ip} "$arg2"\n') 
                f.write(f'  echo ""\n')                
            f.write("fi\n\n")
        
        # Ensure monitoring nodes exist
        monitor_nodes = [node for node in nodes_data if node["type"] == "Monitoring"]
        if monitor_nodes:
            f.write('if [ "$arg1" == "Monitor" ]; then\n')
            for node in monitor_nodes:
                ip = node["ip"]
                f.write(f'  echo "ssh ubuntu@{ip} >>"\n')
                f.write(f'  ssh -o StrictHostKeyChecking=no ubuntu@{ip} "$arg2"\n')
                f.write(f'  echo ""\n')                
                generate_monitor_url_script(node["ip"]) # Generate the monitoring script :)
                os.chmod(f"{base_path}/monitor.sh", 0o750)
            f.write("fi\n")
        # Last echo to add a new line after the output
    
    # Change the permissions to 750
    os.chmod(f"{base_path}/{script_name}", 0o750)
    print(f"Generated script: {script_name}")

# Load configuration from the variables.yaml file
base_path = "../.."
with open(f'{base_path}/variables.yml', 'r') as file:
    config = yaml.safe_load(file)

# Extract project name (cluster_name) from the YAML configuration
project_name = config['cluster_name']

# Define the target directory for the SSH scripts
target_directory = f'{base_path}/ssh_scripts'

# Ensure the output directory exists
os.makedirs(target_directory, exist_ok=True)

# Delete all existing *.sh files in the target directory
sh_files = glob.glob(os.path.join(target_directory, '*.sh'))
for sh_file in sh_files:
    os.remove(sh_file)
    print(f"Deleted script: {sh_file}")

# Initialize a session using Boto3
session = boto3.Session(region_name='us-east-1')
ec2 = session.resource('ec2')

# Filter instances based on the tags
instances = ec2.instances.filter(
    Filters=[
        {'Name': 'tag:Project', 'Values': [project_name]},
        {'Name': 'instance-state-name', 'Values': ['running']}
    ]
)

nodes_data = []
# Loop through each instance and generate SSH scripts
for instance in instances:
    instance_type = None
    az = instance.placement['AvailabilityZone'][-2:]
    public_ip = instance.public_ip_address
    instance_name = None

    # Get the value of the 'Type' and 'Name' tags
    for tag in instance.tags:
        if tag['Key'] == 'Type':
            instance_type = tag['Value']
        if tag['Key'] == 'Name':
            instance_name = tag['Value']

    if instance_type and instance_name:
        # Extract digits from the rightmost side of the instance name
        match = re.search(r'(\d+)$', instance_name)
        instance_name_suffix = match.group(1) if match else ""

        # Generate the script content
        script_content = f"ssh -o StrictHostKeyChecking=no ubuntu@{public_ip}\n"
        nodes_data.append({"type": instance_type, "ip": public_ip})
        # Generate the script file name with the additional suffix
        script_filename = f"{instance_type}-{instance_name_suffix}-{az}.sh".lower()
        script_filepath = os.path.join(target_directory, script_filename)

        # Write the content to the script file
        with open(script_filepath, 'w') as script_file:
            script_file.write(script_content)

        # Change the permissions to 750
        os.chmod(script_filepath, 0o750)

        print(f"Generated script: ssh_scripts/{script_filename}")

#Generate a master shell script to run commands on all the nodes. Faisal, 2024-08-24
generate_run_script(nodes_data)

print("All scripts generated successfully!")
