import re
import requests
import yaml

import sys
sys.path.append('../../python_lib')
from helper_functions import box_print

from packaging import version
from pathlib import Path

# Define file paths
CFG_FILE = "./../../variables.yml"
ANSIBLE_INVENTORY_TEMPLATE_FILE = "./servers.aws_ec2.yaml.tpl"
ANSIBLE_INVENTORY_OUTPUT_FILE = "./inventory/servers.aws_ec2.yaml"
ANSIBLE_CONFIG_TEMPLATE_FILE = "./ansible.cfg.tpl"
ANSIBLE_CONFIG_OUTPUT_FILE = "./ansible.cfg"
ANSIBLE_GET_MONITORING_CONFIG_FILE = "./get_monitoring_config.yml.tpl"
ANSIBLE_GET_MONITORING_CONFIG_OUTPUT_FILE = "./get_monitoring_config.yml"

# Function to clean variable values
def clean_value(value):
    value = value.split('#')[0].strip()  # Remove everything after "#" to ignore comments
    value = value.strip('"').strip("'")  # Remove any surrounding quotes
    return value

def write_output_file(PATH, contents):
    # Write the updated content to the output file
    with open(PATH, "w") as output_file:
        output_file.write(contents)

def load_template_file_inventory(template_path, variables):
    with open(template_path, 'r') as file:
        template = file.read()
    #print("Regions found:", variables['regions'].keys())  # Debug output
    # Generate regions content properly formatted as a YAML list
    regions_content = "\n".join(f" - {region}" for region in variables['regions'].keys())
    #print("Formatted Regions Content:\n", regions_content)  # Debug output
    
    # Replace the placeholder in the template with the formatted regions content
    content = re.sub(r'{{\s*regions\s*}}', regions_content, template)
    content = re.sub(r'{{\s*cluster_name\s*}}', variables['cluster_name'], content)

    return content

def load_template_file(PATH, variables):
    with open(PATH, "r") as template_file:
        content = template_file.read()
        for key, value in variables.items():
            placeholder = f"{{{{ {key} }}}}"  # Adjusted to match more complex placeholders
            if isinstance(value, list):  # Example condition to convert list to string if needed
                value = ', '.join(map(str, value))
            elif isinstance(value, dict):  # Example condition to convert dict to string if needed
                value = ', '.join([f"{k}={v}" for k, v in value.items()])
            content = content.replace(placeholder, str(value))  # Ensure conversion to string
        return content
# Load variables from the cfg file
variables = {}
with open(CFG_FILE, 'r') as file:
    variables = yaml.safe_load(file)

inventory_content = load_template_file_inventory(ANSIBLE_INVENTORY_TEMPLATE_FILE, variables)
with open(ANSIBLE_INVENTORY_OUTPUT_FILE, "w") as f:
    f.write(inventory_content)
