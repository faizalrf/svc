import boto3
import yaml

def get_instance_ips_and_regions(inventory_file, variables_file):
    # Load the inventory file
    with open(inventory_file, 'r') as file:
        inventory = yaml.safe_load(file)

    # Load the variables file to get the cluster_name
    with open(variables_file, 'r') as var_file:
        variables = yaml.safe_load(var_file)
        cluster_name = variables['cluster_name']

    regions = inventory['regions']
    filters = [
        {'Name': 'instance-state-name', 'Values': ['running']},
        {'Name': f'tag:Project', 'Values': [cluster_name]}
    ]
    
    ec2_info = []
    ec2_info_full = []

    # Iterate over each region in the inventory
    for region in regions:
        # Initialize boto3 EC2 client
        ec2_client = boto3.client('ec2', region_name=region)

        # Describe instances with filters
        response = ec2_client.describe_instances(Filters=filters)

        # Extract the private IPs and regions, filtering by the required groups
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                private_ip = instance.get('PrivateIpAddress')
                instance_tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                group = instance_tags.get('Group')

                # Filter instances by the required groups
                if private_ip and group in ['Seed', 'NonSeed', 'Seed2']:
                    ec2_info.append({
                        'private_ip': private_ip,
                        'region': region
                    })
                # Filter instances by the required groups
                if private_ip and group in ['Seed', 'NonSeed', 'ScyllaScale', 'Seed2']:
                    ec2_info_full.append({
                        'private_ip': private_ip,
                        'region': region
                    })
    
    return ec2_info, ec2_info_full

def generate_monitoring_yaml(instances_info, cluster_name):
    monitoring_config = []

    # Group instances by region
    grouped_by_region = {}
    for info in instances_info:
        region = info['region']
        if region not in grouped_by_region:
            grouped_by_region[region] = []
        grouped_by_region[region].append(info['private_ip'])

    return grouped_by_region

if __name__ == "__main__":
    # Replace with the path to your inventory and variables files
    inventory_file = 'inventory/scylla.aws_ec2.yaml'
    variables_file = '../../variables.yml'

    # Get instance IPs and regions
    instances_info, instance_info_full = get_instance_ips_and_regions(inventory_file, variables_file)

    # Load the variables file to get the cluster_name
    with open(variables_file, 'r') as var_file:
        variables = yaml.safe_load(var_file)
        cluster_name = variables['cluster_name']

    # Generate the monitoring YAML
    grouped_by_region = generate_monitoring_yaml(instances_info, cluster_name)
    grouped_by_region_full = generate_monitoring_yaml(instance_info_full, cluster_name)

    # Write the output to a YAML file with proper formatting and order
    with open('scylla_servers.yml', 'w', encoding='utf-8') as output_file:
        for region, ips in grouped_by_region.items():
            output_file.write(f"- targets:\n")
            for ip in ips:
                output_file.write(f"    - {ip}\n")
            output_file.write(f"  labels:\n")
            output_file.write(f"    cluster: {cluster_name}\n")
            output_file.write(f"    dc: {region}\n")

    # Write the output to a YAML file with proper formatting and order
    with open('scylla_servers_full.yml', 'w', encoding='utf-8') as output_file:
        for region, ips in grouped_by_region_full.items():
            output_file.write(f"- targets:\n")
            for ip in ips:
                output_file.write(f"    - {ip}\n")
            output_file.write(f"  labels:\n")
            output_file.write(f"    cluster: {cluster_name}\n")
            output_file.write(f"    dc: {region}\n")