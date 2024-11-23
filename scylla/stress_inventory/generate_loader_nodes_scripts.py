import string
import boto3
import yaml
import os
import shutil
import math

def load_template(file_path):
    with open(file_path, 'r') as file:
        template = yaml.safe_load(file)
    return template

# May not use this and stick to the exact values
def round_to_nearest_significant(n):
    if n == 0:
        return 0
    
    # Determine the number of digits in the number
    magnitude = int(math.floor(math.log10(abs(n))))
    
    # Calculate the divisor and multiplier
    factor = 10 ** magnitude
    
    # Round the number to the nearest significant figure
    return round(n / factor) * factor

# Clear the stress_inventory directory before proceeding
def clear_stress_inventory(stress_inventory_dir):    
    # Check if the directory exists
    if os.path.exists(stress_inventory_dir):
        # Remove the directory and all its contents
        shutil.rmtree(stress_inventory_dir)
    
    # Recreate the stress_inventory directory
    os.makedirs(stress_inventory_dir, exist_ok=True)

# Function to get nodes by tags and cluster name, and ensure they are running
def get_nodes_by_tag_and_cluster(session, cluster_name, tag_key, tag_value, group_values, region):
    ec2 = session.resource('ec2', region_name=region)
    filters = [
        {'Name': f'tag:{tag_key}', 'Values': [tag_value]},
        {'Name': 'tag:Project', 'Values': [cluster_name]},  # Filter based on the project name (cluster name)
        {'Name': 'instance-state-name', 'Values': ['running']},  # Ensure only running instances are fetched
    ]
    
    if group_values:
        filters.append({'Name': 'tag:Group', 'Values': group_values})  # Apply Group filter if provided
    
    instances = ec2.instances.filter(Filters=filters)
    
    instances_list = list(instances)  # Convert to list to iterate and print
    print(f"Found {len(instances_list)} instances with tag {tag_key}={tag_value} in region {region} and group {group_values}")
    
    return instances_list

# Function to extract relevant information from instances
def get_instance_info(instance):
    return {
        'id': instance.id,
        'name': next((tag['Value'] for tag in instance.tags if tag['Key'] == 'Name'), 'Unnamed'),
        'private_ip': instance.private_ip_address,
        'public_ip': instance.public_ip_address if instance.public_ip_address else 'N/A',  # Handle missing public IP
        'zone': instance.placement['AvailabilityZone']  # Use full Availability Zone
    }

def generate_stress_profiles(data_dump, template_file_path):
    counter = 0    
    for data in data_dump:
        output_directory = f"./files/{data['loader_zone']}/{data['loader_name']}"  # Directory to save the generated scripts
        
        # Ensure the output directory exists
        os.makedirs(output_directory, exist_ok=True)

        # Open the file as for string manipulation
        with open(template_file_path, 'r') as file:
            template_content = file.read()

        # Extract the keyspace_definition from the template
        keyspace_definition_start = "keyspace_definition: |"
        keyspace_start = None
        lines = template_content.splitlines()

        for i, line in enumerate(lines):
            if line.strip().startswith(keyspace_definition_start):
                keyspace_start = lines[i + 1].strip()
                break

        if keyspace_start:
            # Modify the keyspace creation statement based on the tablets_enabled flag in data
            if data['tablets_enabled']:
                keyspace_modified = f"{keyspace_start[:-1]} AND tablets = {{'enabled': true}};"
            else:
                keyspace_modified = keyspace_start
            
            # Replace the original keyspace definition in the template content
            template_content = template_content.replace(keyspace_start, keyspace_modified)

        # Create a Template object
        template = string.Template(template_content)

        # Replace the start and end population numbers with the values calculated
        script_content = template_content
        #.safe_substitute(start=data['population_start'], end=data['population_end'])

        script_filename = f"cyclist_seq_{data['loader_name']}_i{data['profile_instance']}.yaml"
        script_filepath = os.path.join(output_directory, script_filename)
        
        with open(script_filepath, 'w') as script_file:
            script_file.write(script_content)
        
        if counter < data['loader_processes']:
            generate_loader_scripts(data, output_directory, script_filename)
        
        if counter < data['stress_processes']:
            generate_stresstest_scripts(data, output_directory, script_filename)
        
        # Generate only one set of scripts
        if counter == 0:
            generate_stepped_kops_test(data, output_directory, script_filename)

        counter += 1

def generate_loader_scripts(data, output_directory, yaml_script_filename):
    # Generate the shell scripts
    profile_instance = data['profile_instance']
    throttle = data['loader_test_throttle']

    script_filename = f"loader_{profile_instance}.sh"

    script_filepath = os.path.join(output_directory, script_filename)
    throttle = math.trunc(throttle / (data['loader_node_count'] * data['loader_processes']))  # Balance throttling based on the number of loader and instances

    with open(script_filepath, 'w') as script_file:
        log_file = f'scylla_loader_{profile_instance + 1}_$(date "+%Y-%m-%d_%H%M%S").log'
        script_file.write(f"#!/bin/bash\n\n")
        script_file.write(f"log_file=\"{log_file}\"\n\n")
        
        population_steps = data['population_steps']
        loader_threads = data['loader_threads']
        scylla_private_ip = data['scylla_private_ip']
        consistency_level = data['consistency_level']
        
        script_text = f"nohup cassandra-stress user profile={yaml_script_filename} cl={consistency_level} n={population_steps} "\
                        f"'ops(insert=1)' no-warmup -rate threads={loader_threads} throttle={throttle}/s "\
                        f"-node {scylla_private_ip} -port native=9042> $log_file 2>&1 &\n"
        
        script_file.write(script_text)

def generate_stresstest_scripts(data, output_directory, yaml_script_filename):
    # Generate the shell scripts
    profile_instance = data['profile_instance']
    throttle = data['stress_test_throttle']
    script_filename = f"stresstest_{profile_instance}.sh"

    script_filepath = os.path.join(output_directory, script_filename)
    
    # Split the read/write stresstest ratio
    writes, reads = map(int, data['stress_ratio'].split(':'))
    
    stress_query = data['stress_query']
    stress_duration = data['stress_duration']
    stress_threads = data['stress_threads']
    consistency_level = data['consistency_level']
    throttle = math.trunc(throttle / (data['loader_node_count'] * data['stress_processes']))  # Balance throttling based on the number of loader and instances

    with open(script_filepath, 'w') as script_file:
        log_file = f"stresstest_{profile_instance + 1}_$(date \"+%Y-%m-%d_%H%M%S\").log"
        script_file.write(f"#!/bin/bash\n\n")
        script_file.write(f"log_file=\"{log_file}\"\n\n")

        script_text = f"nohup cassandra-stress user profile={yaml_script_filename} cl={consistency_level} duration={stress_duration} "\
                        f"'ops(insert={writes},{stress_query}={reads})' no-warmup -rate threads={stress_threads} throttle={throttle}/s "\
                        f"-node {data['scylla_private_ip']} -port native=9042> $log_file 2>&1 &\n\n"
        
        script_file.write(script_text)

def generate_stepped_kops_test(data, output_directory, yaml_script_filename):
    #'stepping_start': config['stress_setup']['stepped_stress_test_start'],  #20k
    #'stepping_end': config['stress_setup']['stepped_stress_test_end'],      #500k
    #'stepping_step': config['stress_setup']['stepped_stress_test_step']     #20k

    for throttle in range(data['stepping_start'], data['stepping_end']+1, data['stepping_step']):
        # Generate the shell scripts
        base_throttle = throttle
        profile_instance = data['profile_instance']
        script_filename = f"step_stresstest_{profile_instance}-{base_throttle:07}.sh"

        script_filepath = os.path.join(output_directory, script_filename)
        
        # Split the read/write stresstest ratio
        writes, reads = map(int, data['stress_ratio'].split(':'))
        
        stress_query = data['stress_query']
        stress_duration = data['stress_duration']
        stress_threads = data['stress_threads']
        consistency_level = data['consistency_level']
        throttle = math.trunc(base_throttle / data['loader_node_count'])  # Per loader trottling. If 10k total throttle, 3 nodes will be 10k/3 per node
        with open(script_filepath, 'w') as script_file:
            log_file = f"step_stresstest_{profile_instance + 1}_{base_throttle}_$(date \"+%Y-%m-%d_%H%M%S\").log"
            script_file.write(f"#!/bin/bash\n\n")
            script_file.write(f"log_file=\"{log_file}\"\n\n")

            script_text = f"cassandra-stress user profile={yaml_script_filename} cl={consistency_level} duration={stress_duration} "\
                            f"'ops(insert={writes},{stress_query}={reads})' no-warmup -rate threads={stress_threads} throttle={throttle}/s "\
                            f"-node {data['scylla_private_ip']} -port native=9042> $log_file 2>&1\n\n"
            
            script_file.write(script_text)

# Fetch `scale_nodes` values from the `regions` dictionary
def get_counts(config, value):
    count = 0
    for region_name, region_config in config["regions"].items():
        if value in region_config:
            count += region_config[value]
    return count

def estimate_row_size(template):
    # Define the size of each data type (in bytes)
    data_type_sizes = {
        'text': 0,  # Variable size, calculated based on the provided size range
        'int': 4,
        'uuid': 16
    }

    estimated_size = 0

    for column in template['columnspec']:
        column_size = 0

        size_range = column['size'].upper().replace('FIXED(', '').replace(')', '').split('..')
        min_size = int(size_range[0])
        max_size = int(size_range[0])
        column_size = round((max_size + min_size) / 2)
        print (f"Field size {column_size}, min {min_size}, max{max_size}")

        estimated_size += column_size # Additional overhead
    return estimated_size

def main():
    # Load configuration from the variables.yml file
    with open('../variables.yml', 'r') as file:
    #with open('/Users/faisal.saeed/Work/scylla-cassandra-testing-framework/variables.yml', 'r') as file:
        config = yaml.safe_load(file)

    # Extract the cluster name
    cluster_name = config['cluster_name']

    # Initialize Boto3 session
    session = boto3.Session()

    startPopulation = 0
    num_loader_instances = config['stress_setup']['number_of_loader_instances']  # Number of initial data loading processes per Loader node
    num_stress_instances = config['stress_setup']['number_of_stress_instances']  # Number of stress testing processes per Loader node

    # Calculate Steps here instead of reading from the config
    OneTiB = 1024 * 1024 * 1024 * 1024 # Bytes 

    loader_node_count = get_counts(config, "loaders")
    total_loader_instances_on_cluster = loader_node_count * num_loader_instances   # based on total loader nodes across Region

    # Compression ratio observed from previous tests
    compression_ratio = 0.425  # This is your observed compression ratio

    # Open the keyspace template processing and generating new scripts
    template_file_path = './cyclist_keyspace.yaml.tp'
    #template_file_path = '/Users/faisal.saeed/Work/scylla-cassandra-testing-framework/stress_inventory/cyclist_keyspace.yaml.tp'
    template = load_template(template_file_path)
    estimated_row_size = (estimate_row_size(template))

    if estimated_row_size <= 0:
        estimated_row_size = 1

    total_scylla_nodes = get_counts(config, "nodes") # Total node count across the Region
    desired_node_size_compressed = config['stress_setup']['desired_node_size'] * OneTiB
    effective_uncompressed_size = desired_node_size_compressed / compression_ratio
    
    # Calculate the total number of rows needed for this uncompressed size
    desired_total_rows = math.trunc(effective_uncompressed_size / estimated_row_size)
    
    # Avoid division by zero
    if total_loader_instances_on_cluster <= 0:
        total_loader_instances_on_cluster = 1

    # Rows to be inserted per loader instance
    population_step = math.trunc(desired_total_rows / total_loader_instances_on_cluster)

    print (f"Number of Loaders {get_counts(config, 'loaders')}, number of loader instances {num_loader_instances}, total scylla nodes {total_scylla_nodes}, Estimated Row Size {estimated_row_size}b, desired node size {config['stress_setup']['desired_node_size']}Tb, Estimated rows to be inserted by each loader instance {population_step}")

    population_steps = population_step
    endPopulation = population_step

    # Define the Group tag values to filter for Scylla nodes
    scylla_group_values = ['Seed', 'NonSeed', 'Seed2']

    max_number_of_instances = max(num_loader_instances, num_stress_instances)   # Which value is greater? We need to create that many cassandra-stress profiles

    for region_name in config['regions']:
        num_loader_machines = config['regions'][region_name]['loaders']
        # Get Loader instances in the current region, filtered by cluster name
        loader_instances = get_nodes_by_tag_and_cluster(session, cluster_name, 'Type', 'Loader', None, region_name)
        
        # Get Scylla instances in the current region, filtered by Group tag
        scylla_instances = get_nodes_by_tag_and_cluster(session, cluster_name, 'Type', 'Scylla', scylla_group_values, region_name)
        
        # Get Loader and Scylla node information
        loader_nodes = [get_instance_info(instance) for instance in loader_instances]
        scylla_nodes = [get_instance_info(instance) for instance in scylla_instances]

        # Sort both lists by 'name' and 'zone' for easier matching 
        loader_nodes.sort(key=lambda x: (x['zone'], x['name']))
        scylla_nodes.sort(key=lambda x: (x['zone'], x['name']))

        # Match Loader and Scylla nodes by exact Availability Zone
        matched_nodes = []
        zones = set()

        # Clear the stress_inventory directory/fies at the start of the script
        clear_stress_inventory('./files/')

        # Path to your inventory and directory, this inventory is to transfer all the generated files to the loaders appropriate loader nodes
        base_dir = './files'
        inventory_file = f'{base_dir}/ansible_inventory.ini'
        playbook_file = f'{base_dir}/playbook.yml'

        # Initialize a dictionary to hold playbook content to transfer the generated scripts to the loader nodes
        playbook_content = []

        # Start writing the inventory for the generated files
        with open(inventory_file, 'w') as inv_file:  # Use 'w' to open the file in write mode
            inv_file.write("[all_loaders]\n")  # Write this only once

        # Search and delete all the existing .sh and .yml files on teh remote hosts before copy the new ones. Faisal, 2024-08-24
        with open(playbook_file, 'w') as pb_file:
            pb_file.write("---\n"
                          "- name: Transfer files to all loader hosts\n"
                          "  hosts: all_loaders\n"
                          "  gather_facts: no\n"
                          "  tasks:\n"
                          "    - name: Find all .sh and .yaml files in the home directory\n"
                          "      ansible.builtin.find:\n"
                          "        paths: /home/ubuntu/\n"
                          "        recurse: yes\n"
                          "        patterns:\n"
                          "          - '*.sh'\n"
                          "          - '*.yaml'\n"
                          "      register: files_to_delete\n"
                          "      no_log: true\n"
                          "    - name: Delete all .sh and .yaml files\n"
                          "      ansible.builtin.file:\n"
                          "        path: '{{ item.path }}'\n"
                          "        state: absent\n"
                          "      loop: '{{ files_to_delete.files }}'\n"
                          "      when: files_to_delete.matched > 0\n"
                          "      no_log: true\n"
                          "    - name: Copy files to each loader\n"
                          "      copy:\n"
                          "        src: '{{ playbook_dir }}/{{ item.src_folder }}/'\n"
                          "        dest: /home/ubuntu/\n"
                          "        owner: ubuntu\n"
                          "        group: ubuntu\n"
                          "        mode: '0755'\n"
                          "      no_log: true\n"
                          "      with_items:\n")  # Write this only once

        for loader in loader_nodes:
            data_dump = []
            print(f"Zone: {loader['zone']} - Loader Node: {loader['name']}")

            for scylla in scylla_nodes:
                if loader['zone'] == scylla['zone']:
                    print(f"  -> Matching with Scylla Node: {scylla['name']} (Private IP: {scylla['private_ip']})")

                    # Calculate the population range for each loader instance after a match is found
                    profile_instance = 0
                    for instance_index in range(max_number_of_instances):  # Execute for number of instances defined for Loader or Stress instances
                        print(f"  - Population Range for {loader['name']} instance {instance_index + 1}: Start: {startPopulation}, End: {endPopulation}")
                        # The data structure that will be passed to various modules. Not all the needed by all the modules though.
                        data_dump.append({
                            'loader_zone': loader['zone'],
                            'loader_name': loader['name'],
                            'loader_private_ip': loader['private_ip'],
                            'loader_public_ip': loader['public_ip'],
                            'scylla_name': scylla['name'],
                            'scylla_private_ip': scylla['private_ip'],
                            'scylla_public_ip': scylla['public_ip'],
                            'profile_instance': profile_instance,   # To use for yaml script naming as we need instances based on 
                            'population_steps': population_steps,
                            'desired_node_size': config['stress_setup']['desired_node_size'],  # Size in TB
                            'population_start': startPopulation,
                            'population_end': endPopulation,
                            'loader_threads': config['stress_setup']['number_of_loader_threads'],
                            'loader_test_throttle': config['stress_setup']['loader_test_throttle'],
                            'loader_processes': num_loader_instances,   # Number of init loader instances runnining on each loader machine
                            'loader_node_count': loader_node_count,
                            'stress_threads': config['stress_setup']['number_of_stress_threads'],
                            'stress_processes': num_stress_instances,   # Number of stress test instances runnining on each loader machine
                            'consistency_level': config['stress_setup']['consistency_level'],
                            'stress_duration': config['stress_setup']['stress_duration_minutes'],
                            'stress_ratio': config['stress_setup']['ratio'],
                            'stress_query': config['stress_setup']['select_query'],
                            'stress_test_throttle': config['stress_setup']['stress_test_throttle'],
                            'tablets_enabled': config['scylla_params']['enable_tablets'],
                            'query_to_execute': config['stress_setup']['select_query'], # For using in the stress test module as to which query from the profile will be used during the test
                            'stepping_start': config['stress_setup']['stepped_stress_test_start'],  #10k
                            'stepping_end': config['stress_setup']['stepped_stress_test_end'],      #500k
                            'stepping_step': config['stress_setup']['stepped_stress_test_step']     #10k
                        })
                        profile_instance += 1
                        startPopulation = endPopulation 
                        endPopulation += population_step
                    generate_stress_profiles(data_dump, template_file_path)
                    break  # Exit the loop after the first match for each zone

            #Start generating the inventory for the generated files
            with open(inventory_file, 'a') as inv_file:
                inv_file.write(f"{loader['name']} ansible_host={loader['public_ip']} ansible_user=ubuntu\n")
            
            # Start adding the the blocks to the playbook file for each folder which was generated earler
            with open(playbook_file, 'a') as pb_file:
                # The template block to be generated for each loader node and it's respective folder locally to be transferred to the respective loader hosts.
                pb_file.write(f"        - {{ name: '{loader['name']}', src_folder: '{loader['zone']}/{loader['name']}' }}\n")

        #Write the closing criteria to the ansible script
        with open(playbook_file, 'a') as pb_file:
            pb_file.write(f"      when: inventory_hostname == item.name\n")

if __name__ == "__main__":
    main()
