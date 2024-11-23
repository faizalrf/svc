import boto3
import time
import yaml
from tabulate import tabulate
# Code to generate the node status on AWS to ensure all the instances are up and running
def load_config(variables_file):
    with open(variables_file, 'r') as file:
        config = yaml.safe_load(file)
    return config

def get_instance_status(region, cluster_name):
    ec2 = boto3.client('ec2', region_name=region)
    
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Project', 'Values': [cluster_name]},
            {'Name': 'instance-state-name', 'Values': ['pending', 'running']}
        ]
    )
    
    instance_statuses = {}
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            instance_state = instance['State']['Name']
            instance_type = instance['InstanceType']
            public_ip = instance.get('PublicIpAddress', 'N/A')
            instance_statuses[instance_id] = {
                'state': instance_state,
                'type': instance_type,
                'public_ip': public_ip
            }
    
    return instance_statuses

def print_instance_statuses(all_statuses):
    table = []
    headers = ['Region', 'Instance ID', 'Instance Type', 'State', 'Public IP']
    
    for region, instances in all_statuses.items():
        for instance_id, status in instances.items():
            table.append([region, instance_id, status['type'], status['state'], status['public_ip']])
    
    print(tabulate(table, headers, tablefmt="pretty"))

def wait_for_all_instances_ready(config, timeout=300, interval=30):
    cluster_name = config['cluster_name']
    start_time = time.time()
    
    while True:
        all_ready = True
        all_statuses = {}
        
        for region in config['regions']:
            print(f"Checking instances in region: {region}")
            region_statuses = get_instance_status(region, cluster_name)
            all_statuses[region] = region_statuses
            
            for instance_id, status in region_statuses.items():
                if status['state'] != 'running':
                    all_ready = False
        
        print_instance_statuses(all_statuses)
        
        if all_ready:
            print("All instances are up and running!")
            break
        
        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout:
            print("Timeout reached. Some instances are still not ready.")
            break
        
        print(f"Waiting for {interval} seconds before next check...")
        time.sleep(interval)

if __name__ == "__main__":
    inventory_file = 'inventory/scylla.aws_ec2.yaml'
    variables_file = '../../variables.yml'

    config = load_config(variables_file)
    
    wait_for_all_instances_ready(config, timeout=300, interval=30)