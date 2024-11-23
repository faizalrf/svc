import json
import os
import re
import random
import time
import sys
sys.path.append('../../python_lib')
from helper_functions import box_print

from terrascript import Terrascript
import terrascript.provider as provider
from terrascript.aws.r import aws_vpc, aws_subnet, aws_instance, aws_vpc_peering_connection, aws_vpc_peering_connection_accepter,aws_security_group,aws_internet_gateway,aws_route_table,aws_route_table_association,aws_route
from terrascript.aws.d import aws_ami , aws_availability_zones
from terrascript.aws.r import aws_key_pair  # To create key pairs dynamically on AWS. Faisal 2024-08-23
import boto3  # To read the zone details from AWS. Faisal, 2024-08-15
import yaml

# Define the ingress rules as a local variable
ingress_rules = [
    {"from_port": 443, "to_port": 443, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "HTTPS access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 3000, "to_port": 3000, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "Monitoring access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 80, "to_port": 80, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "HTTP access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "SSH access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 9042, "to_port": 9042, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "CQL access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 9142, "to_port": 9142, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "SSL CQL access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 7000, "to_port": 7000, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "RPC access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 7001, "to_port": 7001, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "RPC SSL access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 7199, "to_port": 7199, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "JMX access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 10000, "to_port": 10000, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "REST access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 9180, "to_port": 9180, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "Prometheus access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 9100, "to_port": 9100, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "Node exp access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 9160, "to_port": 9160, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "Thrift access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
    {"from_port": 19042, "to_port": 19042, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "description": "Shard-aware access", "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False},
]

egress_rules = [
    {
        "from_port": 0,
        "to_port": 0,
        "protocol": "-1",
        "cidr_blocks": ["0.0.0.0/0"],
        "description": "Allow all outbound traffic",
        "ipv6_cidr_blocks": [],
        "prefix_list_ids": [],
        "security_groups": [],
        "self": False
    }
]

def get_azs(region, ts):
    azs = aws_availability_zones(f"azs_{region}", provider=region)
    ts += azs  # This adds the data source to the script
    return azs.names

def create_infrastructure(config, scylla_params):
    ts = Terrascript()

    # Initialize AWS provider for each specified region
    for region in config['regions']:
        ts += provider.aws(alias=region, region=region)

    if len(config['regions']) > 1:
        resources = {
            "aws_vpc": {},
            "aws_subnet": {},
            "aws_instance": {},
            "aws_vpc_peering_connection": {},
            "aws_vpc_peering_connection_accepter": {},
            "aws_security_group": {},
            "aws_internet_gateway": {},
            "aws_route_table" : {},
            "aws_route_table_association": {},
            "aws_route" : {},
            "aws_key_pair": {}
        }
    else: 
        resources = {
            "aws_vpc": {},
            "aws_subnet": {},
            "aws_instance": {},
            "aws_security_group": {},
            "aws_internet_gateway": {},
            "aws_route_table" : {},
            "aws_route_table_association": {},
            "aws_route" : {},
            "aws_key_pair": {}
        }
    data = {"aws_ami": {}}
    vpc_ids = {}  # Correctly initializing the dictionary to store VPC IDs.
    seed_instances = {}
    primary_region = list(config['regions'].keys())[0]  # Automatically assign the first region as primary

    # Display the regions selected for deployment. Faisal, 2024-08-16
    if len(config['regions']) > 1:
        box_print(f"Multi Region deployment for {list(config['regions'].keys())}")

    for region in config['regions']:
        details = config['regions'][region]
        num_nodes = details['nodes']
        scale_nodes = details['scale_nodes'] # a new variable to identify, how many nodes to scale to. Set this to 0 for no scaling. Faisal, 2024-08-08
        num_nodes += scale_nodes # This will determine how many nodes in total. Faisal, 2024-08-08
        num_loaders = details['loaders']
        loaders_type = details['loaders_type']
        scylla_type = details['scylla_node_type']
        scylla_scale_type = details['scylla_scale_node_type'] # This will determine the type of the scalled out nodes. Faisal, 2024-08-08
        key_name = f"key_pair_{region}_sa_{config['cluster_name']}"     # Create a unique key pair name. Faisal, 2024-08-23
        monitoring_type = config['monitoring_type']
        #key_col_metrics_enabled = config['enable_keyspace_column_metrics']
        cidr = details['cidr']
        #tags = {"Name": f"{config["cluster_name"]}"+ "_" + f"{region}-VPC", "Type": "VPC","Project": config['cluster_name']}
        tags = {"Name": f'{config["cluster_name"]}_{region}-VPC', "Type": "VPC", "Project": config['cluster_name']}  #Fixed the fstring handling to support global python 
        vpc_id = f"vpc_{region}"
        vpc = aws_vpc(vpc_id, provider=region, cidr_block=cidr, enable_dns_support=True, enable_dns_hostnames=True,tags=tags)
        ts += vpc
        resources["aws_vpc"][vpc_id] = {
            "provider": f"aws.{region}",
            "cidr_block": cidr,
            "enable_dns_support": True,
            "enable_dns_hostnames": True,
            "tags": tags
        }

        # Create key pair resource based on the local keys. Faisal, 2024-08-23
        with open(os.path.expanduser(config['path_to_key']), 'r') as pub_key_file:
            public_key_content = pub_key_file.read().strip()

        key_pair_id = f"key_pair_{region}"
        key_pair_resource = aws_key_pair(
            key_pair_id,
            provider=f"aws.{primary_region}",
            key_name=key_name,
            public_key=public_key_content
        )
        ts += key_pair_resource
        resources["aws_key_pair"][key_pair_id] = {
            "provider": f"aws.{primary_region}",
            "key_name": key_name,
            "public_key": public_key_content
        }
        # End Key Pair block

        # Internet Gateway
        igw_id = f"igw_{region}"
        igw = aws_internet_gateway(
            igw_id,  provider = f"aws.{region}",
            vpc_id=f"${{aws_vpc.{vpc_id}.id}}",
            tags={
                "Name": f"{config['cluster_name']}-{region}-IGW",
                "Region": region
            },
            depends_on=[f"aws_vpc.{vpc_id}"]  # Ensure the VPC is created first
        )
        ts += igw
        resources["aws_internet_gateway"][igw_id] = {
            "vpc_id": f"${{aws_vpc.{vpc_id}.id}}", "provider": f"aws.{region}",
            "tags": {
                "Name": f"{config['cluster_name']}-{region}-IGW",
                "Region": region
            },
            "depends_on": [f"aws_vpc.{vpc_id}"]
        }

        # Route Table
        route_table_id = f"rt_{region}"
        route_table = aws_route_table(
            route_table_id, provider = f"aws.{region}",
            vpc_id=f"${{aws_vpc.{vpc_id}.id}}",
            tags={
                "Name": f"{config['cluster_name']}-{region}-RouteTable",
                "Region": region
            },
            depends_on=[f"aws_vpc.{vpc_id}", f"aws_internet_gateway.{igw_id}"]  # Ensure the VPC and IGW are created first
        )
        ts += route_table
        resources["aws_route_table"][route_table_id] = {
            "vpc_id": f"${{aws_vpc.{vpc_id}.id}}", "provider": f"aws.{region}",
            "tags": {
                "Name": f"{config['cluster_name']}-{region}-RouteTable",
                "Region": region
            },
            "depends_on": [f"aws_vpc.{vpc_id}", f"aws_internet_gateway.{igw_id}"]
        }

        # Route
        route = aws_route(
            f"route_{region}",
            provider= f"aws.{region}",
            route_table_id=f"${{aws_route_table.{route_table_id}.id}}",
            destination_cidr_block="0.0.0.0/0",
            gateway_id=f"${{aws_internet_gateway.{igw_id}.id}}",
            depends_on=[f"aws_internet_gateway.{igw_id}",f"aws_route_table.{route_table_id}"]  # Ensure the route table is ready
        )
        ts += route
        resources["aws_route"][f"route_{region}"] = { "provider": f"aws.{region}",
            "route_table_id": f"${{aws_route_table.{route_table_id}.id}}",
            "destination_cidr_block": "0.0.0.0/0",
            "gateway_id": f"${{aws_internet_gateway.{igw_id}.id}}",
            "depends_on": [f"aws_internet_gateway.{igw_id}",f"aws_route_table.{route_table_id}"]
        }                                                                                                                               
        
        azs = aws_availability_zones(f"azs_{region}",state="available")
        
        ts += azs
        az_mode = details.get('az_mode', 'single-az')
        box_print(f"The region to process is {region}")

        # Create a session using the AWS SDK for Python (boto3) to fetch Region details. Faisal, 2024-08-16
        session = boto3.Session(region_name=region)

        # Use the EC2 client to describe availability zones
        ec2_client = session.client('ec2')
        response = ec2_client.describe_availability_zones(Filters=[{'Name': 'state', 'Values': ['available']}])

        # Extract the names of the availability zones, better than manually hardcoding the zones, if muklti AZ then fetch first thee zone names else just the first one. Faisal, 2024-08-15
        complete_az = [az['ZoneName'] for az in response['AvailabilityZones']]
        box_print(f"Complete list of AZs in {region} is {complete_az}")

        if az_mode == 'multi-az':
            azs = [az['ZoneName'] for az in response['AvailabilityZones']][:3]  # Capped to 1st three AZ from the Region. Faisal, 2024-08-15
        else:
            azs = [random.choice([az['ZoneName'] for az in response['AvailabilityZones']][:3])]  # Randomly select an AZ from the first 3. Faisal, 2024-08-15
        
        box_print(f"Zones selected for this setup are {azs}")
        time.sleep(1)

        # End block to get real AZ values. Faisal, 2024-08-16
        
        vpc_ids[region] = vpc_id  # Storing each VPC ID with its respective region as key

        # Create security group resource
        sg_id = f"sg_{region}"
        sg = aws_security_group(
            sg_id,
            provider=f"aws.{region}",
            name=f"{config['cluster_name']}-sg-{region}",
            vpc_id=f"${{aws_vpc.{vpc_id}.id}}",
            ingress=ingress_rules,
            egress=egress_rules,
            tags={
                "Name": f"{config['cluster_name']}-SG-{region}",
                "Project": config['cluster_name'],
                "Type": "Security Group",
                "Region": region
            }
        )
        ts += sg
        
        # Add security group to resources dictionary
        resources["aws_security_group"][sg_id] = {
            "name": f"{config['cluster_name']}-sg-{region}",
            "provider": f"aws.{region}",
            "vpc_id": f"${{aws_vpc.{vpc_id}.id}}",
            "ingress": ingress_rules,
            "egress": egress_rules,
            "tags": {
                "Name": f"{config['cluster_name']}-SG-{region}",
                "Project": config['cluster_name'],
                "Type": "Security Group",
                "Region": region
            }
        }
        # Create subnets within each VPC
        base_octet = int(cidr.split('.')[2])
        subnet_ids = []  # List to store subnet IDs. Faisal, 2024-08-15

        #for i in range(num_nodes):
        for i in range(len(azs)):
            az = azs[i % len(azs)]
            
            subnet_id = f"subnet_{region}_{i}"
            subnet_cidr = f"{cidr.rsplit('.', 2)[0]}.{i}.0/24"  # Example subnet CIDR
            subnet = aws_subnet(
                subnet_id, provider=region, 
                vpc_id=vpc_id,
                cidr_block=subnet_cidr, 
                availability_zone=az,
                map_public_ip_on_launch=True,
                tags={"Name": f"{config['cluster_name']}_{region}_subnet_{i}", "Type": "Subnet","Project": config['cluster_name']}
            )
            ts += subnet
            resources["aws_subnet"][subnet_id] = {
                "provider": f"aws.{region}",
                "vpc_id": f"${{aws_vpc.{vpc_id}.id}}",
                "cidr_block": subnet_cidr,
                "map_public_ip_on_launch": True,
                "availability_zone": az,
                "tags": tags
            }
            
            # Build up a list of subnet ids which will be used later in creating the instances and loaders. Faisal, 2024-08-15
            subnet_ids.append(subnet_id)

            subnet_association_id = f"rta_{region}_{i}"
            subnet_association = aws_route_table_association(
                subnet_association_id,
                subnet_id=f"${{aws_subnet.{subnet_id}.id}}",
                route_table_id=f"${{aws_route_table.{route_table_id}.id}}",
                depends_on=[f"aws_subnet.{subnet_id}", f"aws_route_table.{route_table_id}"],
                provider=f"aws.{region}",
            )
            ts += subnet_association
            resources["aws_route_table_association"][subnet_association_id] = { "provider": f"aws.{region}",
                "subnet_id": f"${{aws_subnet.{subnet_id}.id}}",
                "route_table_id": f"${{aws_route_table.{route_table_id}.id}}",
                "depends_on": [f"aws_subnet.{subnet_id}", f"aws_route_table.{route_table_id}"]
            }

        # ScyllaDB AMI
        scylla_ami_id = f"scylla_ami_{region}"
        scylla_ami = aws_ami(scylla_ami_id, provider=region, most_recent=True,
                             filter=[{"name": "name", "values": [f"ScyllaDB* {config['scylla_version']}"]},
                                      {"name": "virtualization-type", "values": ["hvm"]},
                                      {"name": "root-device-type", "values": ["ebs"]},
                                      {"name": "architecture", "values": ["x86_64"]}],
                             owners=["158855661827"])
        ts += scylla_ami
        data["aws_ami"][scylla_ami_id] = {
            "provider": f"aws.{region}",
            "most_recent": True,
            "filter": [
                {"name": "name", "values": [f"ScyllaDB* {config['scylla_version']}"]},
                {"name": "virtualization-type", "values": ["hvm"]},
                {"name": "root-device-type", "values": ["ebs"]},
                {"name": "architecture", "values": ["x86_64"]}
            ],
            "owners": ["158855661827"]
        }

        # Ubuntu AMI
        ubuntu_ami_id = f"ubuntu_ami_{region}"
        ubuntu_ami = aws_ami(ubuntu_ami_id, provider=region, most_recent=True,
                             filter=[{"name": "name", "values": ['ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*']},
                                      {"name": "state", "values": ["available"]},
                                      {"name": "architecture", "values": ["x86_64"]},
                                      {"name": "root-device-type", "values": ["ebs"]}],
                             owners=["099720109477"])
        ts += ubuntu_ami
        data["aws_ami"][ubuntu_ami_id] = {
            "provider": f"aws.{region}",
            "most_recent": True,
            "filter": [
                {"name": "name", "values": ['ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*']},
                {"name": "state", "values": ["available"]},
                {"name": "architecture", "values": ["x86_64"]},
                {"name": "root-device-type", "values": ["ebs"]}
            ],
            "owners": ["099720109477"]
        }

        first_region = next(iter(config['regions']))  # Get the first region key from the dictionary
        if region == first_region:
            # Create monitoring instance only for the first region
            monitoring_instance_id = f"monitoring_{region}"
            monitoring_tags = {
                "Name": f"{config['cluster_name']}_{region}_monitoring_0",  # Added a ZERO suffix for consistency. Faisal, 2024-08-14
                "Type": "Monitoring",
                "Project": config['cluster_name']
            }
            
            # Ensure the AMI ID and instance type variables are correctly named and used
            monitoring_instance = aws_instance(
                monitoring_instance_id, provider=region,
                ami=f"${{data.aws_ami.{ubuntu_ami_id}.id}}",  # Assuming ubuntu_ami_id is defined as per the region
                instance_type=monitoring_type,  # Ensure 'monitoring_type' is defined in your region details
                vpc_security_group_ids=[f"${{aws_security_group.{sg_id}.id}}"],
                subnet_id=f"${{aws_subnet.subnet_{region}_0.id}}",  # Example subnet ID for monitoring
                tags=monitoring_tags,
                key_name=key_name,
                depends_on=[f"aws_security_group.{sg_id}", f"aws_key_pair.{key_pair_id}"]
            )
            ts += monitoring_instance
            resources["aws_instance"][monitoring_instance_id] = {
                "provider": f"aws.{region}",
                "ami": f"${{data.aws_ami.{ubuntu_ami_id}.id}}",
                "instance_type": monitoring_type,
                "subnet_id": f"${{aws_subnet.subnet_{region}_0.id}}",
                "vpc_security_group_ids": [f"${{aws_security_group.{sg_id}.id}}"],
                "tags": monitoring_tags,
                "key_name": key_name,
                "depends_on": [f"aws_security_group.{sg_id}", f"aws_key_pair.{key_pair_id}"]
            }

        # This will define what type of Scylla Node it is, Scylla is a normal node, ScyllaScale is a node that will be used for Scaling later. Faisal, 2024-08-08
        scylla_group = "NonSeed"        
        scylla_params['cluster_name'] = config['cluster_name']
        for i in range(num_nodes):
            # Rotate through the stored subnet_ids to distribute instances across subnets/AZs. Faisal, 2024-08-15
            selected_subnet_id = subnet_ids[i % len(subnet_ids)]

            instance_id = f"instance_{region}_{i}"
            
            seed_instances[region] = f"${{aws_instance.{instance_id}.private_ip}}"
            # Check if this is the first instance (seed instance) for the region
            if i == 0:                
                tags = {"Name": f"{config['cluster_name']}_{region}_instance_{i}", "Group": "Seed", "Type": "Scylla","Project": config['cluster_name']}
                if region == primary_region:
                    # This is the primary seed instance, it does not need a seed provider
                    seeds = ""  # No seeds needed for the primary seed itself
                    start_on_boot = "true"

                    ## Properly indent the scylla_yaml_json to align under "scylla_yaml". Faisal, 2024-09-03
                    scylla_yaml_json = json.dumps(scylla_params, indent=28)
                    #scylla_yaml_indented = scylla_yaml_json.replace("\n", "\n                        ")

                    # Added the enable_tablets. Faisal, 2024-08-13
                    user_data_script = f"""
                    {{
                        "scylla_yaml": {scylla_yaml_json},
                        "start_scylla_on_first_boot": {start_on_boot}
                    }}
                    """
                else:
                    tags = {"Name": f"{config['cluster_name']}_{region}_instance_{i}", "Group": "Seed2", "Type": "Scylla","Project": config['cluster_name']}
                    # Use the primary region's seed IP for the first instance of other regions
                    seeds = f"${{aws_instance.instance_{primary_region}_0.private_ip}}"
                    # Build string for Seeders, Faisal 2024-09-03
                    scylla_params['seed_provider'] = [{
                        "class_name": "org.apache.cassandra.locator.SimpleSeedProvider",
                        "parameters": [{
                            "seeds": f"{seeds}"
                        }]
                    }]
                    start_on_boot = "false"

                    ## Properly indent the scylla_yaml_json to align under "scylla_yaml". Faisal, 2024-09-03
                    scylla_yaml_json = json.dumps(scylla_params, indent=28)
                    #scylla_yaml_indented = scylla_yaml_json.replace("\n", "\n                        ")

                    user_data_script = f"""
                        {{
                            "scylla_yaml": {scylla_yaml_json},
                            "start_scylla_on_first_boot": {start_on_boot}
                        }}
                        """
            else:
                # If the original number of nodes have been provisioned, the subsequent nodes are assumed to be for Scaling later. Also set the Scylla Node Group to scaled type. Faisal, 2024-08-08
                if i >= (num_nodes - scale_nodes):
                    scylla_group = "ScyllaScale"
                    scylla_type = scylla_scale_type  # Later when defining the instance type, the scale type will be used for the new nodes, Faisal, 2024-08-08

                tags = {"Name": f"{config['cluster_name']}_{region}_instance_{i}", "Group": scylla_group, "Type": "Scylla","Project": config['cluster_name']}
                # Non-seed instances use the primary seed's IP
                seeds = f"${{aws_instance.instance_{primary_region}_0.private_ip}}"
                start_on_boot = "false"
                # Build string for Seeders, Faisal 2024-09-03
                scylla_params['seed_provider'] = [{
                    "class_name": "org.apache.cassandra.locator.SimpleSeedProvider",
                    "parameters": [{
                        "seeds": f"{seeds}"
                    }]
                }]

                # Properly indent the scylla_yaml_json to align under "scylla_yaml". Faisal, 2024-09-03
                scylla_yaml_json = json.dumps(scylla_params, indent=28)
                # Properly indent the scylla_yaml_json to align under "scylla_yaml". Faisal, 2024-09-03
                #scylla_yaml_indented = scylla_yaml_json.replace("\n", "\n                        ")

                user_data_script = f"""
                    {{
                        "scylla_yaml": {scylla_yaml_json},
                        "start_scylla_on_first_boot": {start_on_boot}
                    }}
                    """
            #instance_id = f"instance_{region}_{i}"
            #Use the the new `scylla_node_type` variable for node definition, this value might be different for scaled nodes based on the configured yml. Faisal, 2024-08-08
            instance = aws_instance(instance_id, provider=region,
                                    ami=f"${{data.aws_ami.{scylla_ami_id}.id}}", instance_type=scylla_type,
                                    vpc_security_group_ids=[f"${{aws_security_group.sg_{region}.id}}"],  # Attach security group
                                    subnet_id=f"${{aws_subnet.{selected_subnet_id}.id}}",user_data=user_data_script,    #Use the saved and rotated selected_subnet_id. Faisal, 2024-08-15
                                    tags=tags,key_name=key_name,
                                    depends_on=[f"aws_security_group.{sg_id}", f"aws_key_pair.{key_pair_id}"])
            ts += instance
            resources["aws_instance"][instance_id] = {
                "provider": f"aws.{region}",
                "ami": f"${{data.aws_ami.{scylla_ami_id}.id}}",
                "instance_type": scylla_type,
                "subnet_id": f"${{aws_subnet.{selected_subnet_id}.id}}",    #Use the saved and rotated selected_subnet_id. Faisal, 2024-08-15
                "vpc_security_group_ids": [f"${{aws_security_group.{sg_id}.id}}"],  # Ensure this is an array
                "user_data": user_data_script,
                "tags": tags,
                "key_name": key_name,
                "depends_on": [f"aws_security_group.{sg_id}", f"aws_key_pair.{key_pair_id}"]
            }

        for i in range(num_loaders):
            # Rotate through the stored subnet_ids to distribute instances across subnets/AZs. Faisal, 2024-08-15
            selected_subnet_id = subnet_ids[i % len(subnet_ids)]

            instance_id = f"loader_{region}_{i}"    #Added the counter for the instance names of the loaders. Faisal, 2024-08-14
            #tags = {"Name": f"{config["cluster_name"]}"+ "_" + f"loader_{region}_{i}", "Type": "Loader","Project": config['cluster_name']}
            tags = {'Name': f"{config['cluster_name']}_loader_{region}_{i}", 'Type': 'Loader', 'Project': config['cluster_name']}  # Bug fix in fstring, Faisal. 2024-08-18
            instance = aws_instance(instance_id, provider=region,
                                    ami=f"${{data.aws_ami.{scylla_ami_id}.id}}", instance_type=loaders_type,    # Changed the AMI to Scylla AMI to keep in sync with the ScyllaDB nodes. Faisal, 2024-09-04
                                    vpc_security_group_ids=[f"${{aws_security_group.{sg_id}.id}}"],  # Attach security group
                                    subnet_id=f"${{aws_subnet.{selected_subnet_id}.id}}",tags=tags,key_name=key_name,depends_on=[f"aws_security_group.{sg_id}",f"aws_key_pair.{key_pair_id}"])    #Use the saved and rotated selected_subnet_id. Faisal, 2024-08-15
            ts += instance
            resources["aws_instance"][instance_id] = {
                "provider": f"aws.{region}",
                "ami": f"${{data.aws_ami.{scylla_ami_id}.id}}",    # Changed the AMI to Scylla AMI to keep in sync with the ScyllaDB nodes. Faisal, 2024-09-04
                "instance_type": loaders_type,
                "subnet_id": f"${{aws_subnet.{selected_subnet_id}.id}}",    #Use the saved and rotated selected_subnet_id. Faisal, 2024-08-15
                "vpc_security_group_ids": [f"${{aws_security_group.{sg_id}.id}}"],  # Ensure this is an array
                "tags": tags,
                "key_name": key_name,
                "depends_on": [f"aws_security_group.{sg_id}", f"aws_key_pair.{key_pair_id}"]
            }

    # Configure VPC Peering Connections if multiple regions are specified
    if len(config['regions']) > 1:
        regions = list(config['regions'].keys())
        box_print(f"Setting up peering between {regions}")
        for i, region_i in enumerate(regions):
            for j in range(i + 1, len(regions)):
                region_j = regions[j]
                peering_id = f"peer_{region_i}_to_{region_j}"
                #tags = {"Name": f"{config["cluster_name"]}"+ "_" + f"peer_{region_i}_to_{region_j}", "Type": "Peering","Project": config['cluster_name']}
                tags = {"Name": f"{config['cluster_name']}_peer_{region_i}_to_{region_j}", "Type": "Peering", "Project": config['cluster_name']}  # Bug fix in fstring, Faisal. 2024-08-18
                peering = aws_vpc_peering_connection(peering_id, provider=region_i,
                                                     vpc_id=f"${{aws_vpc.{vpc_ids[region_i]}.id}}",
                                                     peer_vpc_id=f"${{aws_vpc.{vpc_ids[region_j]}.id}}",
                                                     peer_region=region_j,  # Specify the peer VPC's region
                                                     auto_accept=True,tags=tags)
                ts += peering
                resources["aws_vpc_peering_connection"][peering_id] = {
                    "provider": f"aws.{region_i}",
                    "vpc_id": f"${{aws_vpc.{vpc_ids[region_i]}.id}}",
                    "peer_vpc_id": f"${{aws_vpc.{vpc_ids[region_j]}.id}}",
                    "peer_region": region_j,
                    "tags": tags  # This is critical for cross-region peering
                    #"auto_accept": True
                }
                # Routes for peering in each route table
                route_peer_i = aws_route(f"route_peer_{region_i}_{region_j}", provider=f"aws.{region_i}",
                                        route_table_id=f"${{aws_route_table.rt_{region_i}.id}}",
                                        destination_cidr_block=config['regions'][region_j]['cidr'],
                                        vpc_peering_connection_id=f"${{aws_vpc_peering_connection.{peering_id}.id}}")
                ts += route_peer_i
                resources["aws_route"][f"route_peer_{region_i}_{region_j}"] = route_peer_i

                route_peer_j = aws_route(f"route_peer_{region_j}_{region_i}", provider=f"aws.{region_j}",
                                        route_table_id=f"${{aws_route_table.rt_{region_j}.id}}",
                                        destination_cidr_block=config['regions'][region_i]['cidr'],
                                        vpc_peering_connection_id=f"${{aws_vpc_peering_connection.{peering_id}.id}}")
                ts += route_peer_j
                resources["aws_route"][f"route_peer_{region_j}_{region_i}"] = route_peer_j

                                # Peering connection acceptance in the peer region
                accepter_id = f"peer_accept_{region_j}_from_{region_i}"
                #tags = {"Name": f"{config["cluster_name"]}"+ "_" + f"peer_accept_{region_j}_from_{region_i}", "Type": "peer_accept","Project": config['cluster_name']}
                tags = {"Name": f"{config['cluster_name']}_peer_accept_{region_j}_from_{region_i}", "Type": "peer_accept", "Project": config['cluster_name']}  # Bug fix in fstring, Faisal. 2024-08-18
                accepter = aws_vpc_peering_connection_accepter(accepter_id, provider=region_j,
                                                               vpc_peering_connection_id=f"${{aws_vpc_peering_connection.{peering_id}.id}}",
                                                               auto_accept=True,tags=tags)
                ts += accepter
                resources["aws_vpc_peering_connection_accepter"][accepter_id] = {
                    "provider": f"aws.{region_j}",
                    "vpc_peering_connection_id": f"${{aws_vpc_peering_connection.{peering_id}.id}}",
                    "auto_accept": True,
                    "tags": tags
                }

    tf_config = {
        "terraform": {
            "required_providers": {
                "aws": {
                    "source": "hashicorp/aws",
                    "version": "~> 5.0"
                }
            }
        },
        "provider": {
            "aws": [{"alias": region, "region": region} for region in config['regions']]
        },
        "resource": resources,
        "data": data
    }

    return json.dumps(tf_config, indent=4)

def read_config(file_path):
    # Regular expression pattern to match the cluster_name without quotes and with optional suffix
    pattern = r'(\s*cluster_name:\s*")([a-zA-Z0-9-]+)'

    # Read the entire content of the configuration file
    with open(file_path, "r") as file:
        content = file.read()

    # Check if the cluster_name already has a suffix
    match = re.search(pattern, content)
    if match:
        cluster_name_base = match.group(2)

        # Check if there's already a suffix
        if re.search(r'-\d{3}$', cluster_name_base):
            print(f"Cluster name '{cluster_name_base}' already has a suffix.")
        else:
            # Generate a random 3-digit number with leading zeros
            random_suffix = f"-{random.randint(0, 999):03}"

            # Replace the cluster_name in the content, adding the suffix at the end
            new_content = re.sub(pattern, rf'\1{cluster_name_base}{random_suffix}', content)

            # Write the updated content back to the configuration file
            with open(file_path, "w") as file:
                file.write(new_content)

            print(f"Updated cluster_name: {cluster_name_base}{random_suffix}")
    else:
        print("cluster_name not found in the configuration file.")

    # Load the updated YAML configuration and return it
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

# This method will read from the ansible config template file and append the private keys part from variables.yml and write to ansible.cfg. Faisal, 2024-09-04
def write_ansible_cfg(template_file_path, config):
    # Open the original file for reading
    with open(template_file_path, 'r') as original_cfg_template:
        # Open a new file for writing with a different name
        new_file_path = "../ansible_install/ansible.cfg"  # Change this to your desired new file name
        with open(new_file_path, 'w') as new_file:
            # Read the content of the original file and write it to the new file
            for line in original_cfg_template:
                new_file.write(line)

            # Write the new content at the end of the file
            new_file.write(f"\nprivate_key_file = {config['path_to_private']}\n")
            new_file.write(f"ansible_ssh_private_key_file = {config['path_to_private']}\n")

if __name__ == "__main__":    
    config = read_config("../../variables.yml")
    # Extract scylla_params from the config
    scylla_params = config.get('scylla_params', {})

    write_ansible_cfg("../ansible_install/ansible.cfg.tp", config) # Open Ansible Template for writing the private keys. Faisal, 2024-09-03

    terraform_script = create_infrastructure(config, scylla_params)
    with open('main.tf.json', 'w') as file:
        file.write(str(terraform_script))
