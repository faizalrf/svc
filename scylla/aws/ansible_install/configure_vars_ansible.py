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
ANSIBLE_INVENTORY_TEMPLATE_FILE = "./scylla.aws_ec2.yaml.tpl"
ANSIBLE_INVENTORY_OUTPUT_FILE = "./inventory/scylla.aws_ec2.yaml"
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


# Check the 'availability_zone' variable and set 'subnet_count' accordingly
#print(variables.get("availability_zone"))
# if variables.get("availability_zone") == "Multi":
#     variables["subnet_count"] = "3"
# elif variables.get("availability_zone") == "Single":
#     variables["subnet_count"] = "1"
# else:
#     # Default or error handling if needed
#     print("Warning: 'availability_zone' not set to 'Multi' or 'Single'. Please check your variables.cfg.")

inventory_content = load_template_file_inventory(ANSIBLE_INVENTORY_TEMPLATE_FILE, variables)
with open(ANSIBLE_INVENTORY_OUTPUT_FILE, "w") as f:
    f.write(inventory_content)
    
# content = load_template_file(ANSIBLE_CONFIG_TEMPLATE_FILE, variables)
# write_output_file(ANSIBLE_CONFIG_OUTPUT_FILE, content)

content = load_template_file(ANSIBLE_GET_MONITORING_CONFIG_FILE, variables)
write_output_file(ANSIBLE_GET_MONITORING_CONFIG_OUTPUT_FILE, content)

# Faisal, the versions 4.7 onwards don't follow the `scylla-monitoring` semantics, created new function to pull all the tags
def get_all_tags(owner, repo):
    tags = []
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    while url:
        response = requests.get(url)
        data = response.json()
        tags.extend([tag['name'] for tag in data])
        # Check if there's a next page
        if 'next' in response.links:
            url = response.links['next']['url']
        else:
            url = None
    return tags

def is_valid_version(tag):
    try:
        version.parse(tag)
        return True
    except version.InvalidVersion:
        return False

def get_latest_tag(repo_owner, repo_name):
    all_tags = get_all_tags(repo_owner, repo_name)
    # Strip non-version prefixes and filter out invalid versions
    version_tags = [re.sub(r'^[^\d]*', '', tag) for tag in all_tags]
    valid_version_tags = [tag for tag in version_tags if is_valid_version(tag)]
    valid_version_tags.sort(key=version.parse, reverse=True)
    return valid_version_tags[0] if valid_version_tags else None

def fetch_and_check_latest_tag(repo_owner, repo_name):
    latest_tag = get_latest_tag(repo_owner, repo_name)
    return latest_tag
# Faisal, End of the new functions block

# ## Getting Latest Monitoring Version
# def get_latest_tag(repo_owner, repo_name):
#     api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/tags"
#     response = requests.get(api_url)
#     tags = response.json()
#     version_tags = [tag['name'] for tag in tags]
#     semantic_versions = [ver for ver in version_tags if ver.replace(f"{repo_name}-", "").replace("scylla-monitoring-", "").replace('v', '').replace('_', '.').count('.') == 2]
#     semantic_versions.sort(key=lambda x: version.parse(x.replace(f"{repo_name}-", "").replace("scylla-monitoring-", "").replace('v', '').replace('_', '.')))
#     return semantic_versions[-1] if semantic_versions else "No valid semantic versions found."

# Fetch the latest tag
# latest_tag = get_latest_tag("scylladb", "scylla-monitoring")

# Faisal, Call the updated function to fetch the latest tag
latest_tag = fetch_and_check_latest_tag("scylladb", "scylla-monitoring")
box_print(f"The latest Monitoring stack version is {latest_tag}")

if latest_tag == "No valid semantic versions found.":
    exit()

# Construct the new archive URL with the latest tag
new_url = f"https://github.com/scylladb/scylla-monitoring/archive/refs/tags/{latest_tag}.tar.gz"

# Path to the playbook file
playbook_file_path = Path('./install_monitoring.yml')

# Load the existing content of the playbook
with open(playbook_file_path, 'r') as file:
    playbook_content = yaml.safe_load(file)

# Update the scylla_monitoring_archive_url in the playbook content
# This part needs to be adapted based on the actual structure of your YAML.
# For demonstration, I'm assuming it's a direct key under some task's vars. You might need to navigate the structure accordingly.
updated = False
for task in playbook_content:
    if 'vars' in task and 'scylla_monitoring_archive_url' in task['vars']:
        task['vars']['scylla_monitoring_archive_url'] = new_url
        updated = True
        break

if updated:
    # Write the updated content back to the file
    with open(playbook_file_path, 'w') as file:
        yaml.dump(playbook_content, file)
  #  print("Updated install_monitoring.yml with the latest Scylla Monitoring archive URL.")
# else:
  #  print("Did not find scylla_monitoring_archive_url in the playbook.")