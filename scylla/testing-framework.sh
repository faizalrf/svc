#!/bin/bash
export HOME_DIR=$(pwd)
# Function to print text enclosed in a text box. Faisal, 2024-08-16
box_print() {
    local text_to_print="$1"
    
    horizontal_line="-"
    vertical_line="|"
    top_left="+"
    top_right="+"
    bottom_left="+"
    bottom_right="+"

    # Calculate the length of the text and the print line
    result_length=${#text_to_print}
    total_width=$((result_length + 2))  # Add 2 for the spaces before and after the text
    print_line=$(printf "%-${total_width}s" "" | tr ' ' "$horizontal_line")

    # Print the box
    echo -e "${top_left}${print_line}${top_right}"
    echo -e "${vertical_line} ${text_to_print} ${vertical_line}"
    echo -e "${bottom_left}${print_line}${bottom_right}"

    # Optional sleep for a brief pause
    sleep 1
}

# Function to update scylla_version in YAML file based on cloud provider
update_scylla_version() {
    local provider="$1"
    local yaml_file="variables.yml"  # specify your yaml file path

    # Ensure the file exists
    if [ ! -f "$yaml_file" ]; then
        echo "Error: YAML file does not exist at the specified path: $yaml_file"
        return 1
    fi

    # Extract the current version from the YAML file
    local current_version=$(grep "scylla_version:" $yaml_file | awk -F\" '{print $2}')
    
    # Check extraction success
    if [ -z "$current_version" ]; then
        echo "Error: Failed to extract scylla_version from $yaml_file"
        return 1
    else
        box_print "Current version extracted: $current_version"
    fi

    local formatted_version="$current_version"
    
    # Check if the current version is rc, then don't format it
    if [[ $current_version =~ rc[0-9]$ ]]; then
        box_print "This is a rc version, formatting is not needed!"
    else
        case "$provider" in
            "aws")
                formatted_version="${current_version//-/.}"  # Ensure format uses dots
                ;;
            *)
                echo "Unsupported provider: $provider"
                return 1
                ;;
        esac
    fi

    # Check if reformatting is needed
    if [ "$current_version" == "$formatted_version" ]; then
        box_print "No update needed, scylla_version already formatted for $provider."
    else
        # Update the file using sed according to OS
        box_print "Updating scylla_version for $provider..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/scylla_version: \"$current_version\"/scylla_version: \"$formatted_version\"/" $yaml_file
        else
            sed -i "s/scylla_version: \"$current_version\"/scylla_version: \"$formatted_version\"/" $yaml_file
        fi
        box_print "scylla_version updated from $current_version to $formatted_version."
    fi
}

# Function to test AWS connectivity
aws_test() {
    box_print "Fetching the list of 2024.2.* AMI from AWS"
    AWS_PAGER="" aws ec2 describe-images --filters "Name=name,Values=ScyllaDB* 2024.2*" --query 'Images[*].{ID:ImageId,Name:Name}' --region us-east-1 --output text
    # Check if the command was successful
    if [ $? -eq 0 ]; then
        box_print "The AWS connectivity test was successful."
    else
        box_print "The AWS connectivity test"
    fi
}

# Function to perform AWS setup
aws_setup() {
    set -e
    update_scylla_version "aws"
    cd "$HOME_DIR"/aws/cluster/
    python3 dynamic_aws_setup.py
    # Initialize Terraform (download providers, etc.)
    terraform init
    # Apply the Terraform configuration
    terraform apply -auto-approve
    box_print "Generating ssh_scripts for all the nodes!"
    cd "$HOME_DIR"/aws/cluster/
    python3 generate_ssh_scripts.py # New script to generate the SSH scripts for each node uses the public key file from config. Faisal, 2024-08-19
    set +e
    box_print "System is ready for configuration."
    echo "Next Steps:"
    echo "1. 'cd ssh_scripts' to connect to nodes and review configuration before running the next step"
    echo "2. './scylla-testing-framework.sh aws config' to configure ScyllaDB, Loaders and Monitor nodes"
    echo
}

aws_config() {
    box_print "Cooldown 120s before resumiung Setting up Scylla."
    sleep 120
    set -e
    cd "$HOME_DIR"/aws/ansible_install
    box_print "Waiting for the EC2 instances to start and ready!"
    python3 get_nodes_status.py  # Ensure the cluster is ready without any manual waiting
    box_print "Setting up Scylla, Loaders and Monitor nodes"
    python3 configure_vars_ansible.py
    python3 generate_monitoring_config.py   # To generate monitoring configuration file to match multi-region setup. Faisal, 2024-08-17
    ansible-playbook wait_for_seed.yml
    ansible-playbook stop_scale_nodes.yml   # Stop the nodes created for scaling the cluster. Also enable tablets. Faisal, 2024-08-13 
    ansible-playbook start_nonseed.yml
    ansible-playbook install_monitoring.yml 
    ansible-playbook configure_loader.yml   # The configure_loader will just install the scylla-tools and as it's already using the ScyllaDB AMI
    set +e
    box_print "System is ready for testing."
    echo "Next Steps:"
    echo "1. './scylla-testing-framework.sh aws initload' To run the initial data loader on the cluster"
    echo "2. './scylla-testing-framework.sh aws stresstest' To run the regular read/write stresstest once initload is done"
    echo "3. './scylla-testing-framework.sh aws scaleout' During the stresstest, execute the scaleout to extend the cluster with additional nodes if scaling configured"
    echo "3. './scylla-testing-framework.sh aws scalein' During the stresstest, execute the scalein to scale the cluster in back to the original three nodes"
    echo "4. './scylla-testing-framework.sh aws destroy' Once done with all the testing, destroy to terminate the cloud infrastructure"
    echo
}

aws_generate_stress_setup() {
    box_print "Generating stress test scripts based on the config"
    cd "$HOME_DIR"/stress_inventory
    set -e
    python3 generate_loader_nodes_scripts.py
    # This ansible will transfer all the generated scripts to the related LOADER nodes
    box_print "Transferring the generated files to the loader nodes"
    cd "$HOME_DIR"/stress_inventory/files
    ANSIBLE_CONFIG="$HOME_DIR"/aws/ansible_install/ansible.cfg ansible-playbook -i ansible_inventory.ini playbook.yml
    set +e
}

# New function to scale out the cluster. Faisal, 2024-08-10
aws_scaleout() {
    cd "$HOME_DIR"/aws/ansible_install
    set -e
    box_print "Updating monitoring configuration"
    ansible-playbook restart_monitoring_scaleout.yml
    box_print "Commencing Scale-out of the cluster"
    sleep 5
    ansible-playbook start_scale_nodes.yml
    set +e
    box_print "System has been scaled out."
}

# New function to scale out the cluster. Faisal, 2024-08-10
aws_scalein() {
    cd "$HOME_DIR"/aws/ansible_install
    set -e
    box_print "Updating monitoring configuration"
    ansible-playbook restart_monitoring_scalein.yml
    box_print "Commencing Scale-in of the cluster"
    sleep 5
    ansible-playbook decom_scaled_nodes.yml
    set +e
    box_print "System has been scaled in."
}

aws_initload() {
    box_print "Commencing initial load to the cluster"
    cd "$HOME_DIR"/aws/ansible_install
    set -e
    ansible-playbook kill_cassandra_stress_jobs.yml
    aws_generate_stress_setup   # Generate Sress profiles and scripts
    cd "$HOME_DIR"/aws/ansible_install
    ansible-playbook init_load_generator.yml
    set +e
    box_print "Initial Data Generators Triggered"
}

aws_stresstest() {
    box_print "Commencing the Stress test of the cluster"
    cd "$HOME_DIR"/aws/ansible_install
    set -e
    ansible-playbook kill_cassandra_stress_jobs.yml
    aws_generate_stress_setup   # Generate Sress profiles and scripts
    cd "$HOME_DIR"/aws/ansible_install
    ansible-playbook stresstest_runner.yml
    set +e
    box_print "Stress test Triggered"
}

aws_stepstresstest() {
    box_print "Commencing the Stepped Stress test of the cluster"
    cd "$HOME_DIR"/aws/ansible_install
    set -e
    ansible-playbook kill_cassandra_stress_jobs.yml
    aws_generate_stress_setup   # Generate Sress profiles and scripts
    cd "$HOME_DIR"/aws/ansible_install
    ansible-playbook step_stress_runner.yml
    set +e
    box_print "Stepped Stress test completed"
}

aws_kill_loaders() {
    box_print "Terminating all cassandra-stress jobs"
    cd "$HOME_DIR"/aws/ansible_install
    set -e
    ansible-playbook kill_cassandra_stress_jobs.yml
    set +e
    box_print "All cassandra-stress Terminated on all the Loader Nodes"
}

aws_destroy() {
    box_print "Commencing cluster destruction!"
    set -e
    
    cd "$HOME_DIR"/aws/cluster
    terraform destroy --auto-approve
    
    if [ $? -eq 0 ]; then
        box_print "Scylla's infra has been destroyed"
        rm -rf "$HOME_DIR"/ssh_scripts/*.sh
        box_print "ssh_scripts have been deleted"

        rm -rf "$HOME_DIR"/stress_inventory/files/*
        box_print "Inventory files have been deleted"
    fi
    box_print "Cleanup completed!"
}

# Function to test GCP connectivity
aws_test() {
    clear
    echo "As an example"
    echo "2024.1"
    echo "2024.2"
    read -p "Please key in the Scylla version to search for AMI: " ver
    box_print "Fetching the list of ${ver}* AMI from AWS"
    #AWS_PAGER="" aws ec2 describe-images --filters "Name=name,Values=ScyllaDB* ${ver}*" --query 'Images[*].{ID:ImageId,Name:Name}' --region us-east-1 --output text
    AWS_PAGER="" aws ec2 describe-images --filters "Name=name,Values=ubuntu/images/*/ubuntu-*-24.04-amd64-server-*" --query 'Images[*].{ID:ImageId,Name:Name}' --region us-east-1 --output text
    # Check if the command was successful
    if [ $? -eq 0 ]; then
        box_print "The AWS connectivity test was successful."
    else
        box_print "The AWS connectivity test"
    fi
}

# Main logic to process arguments
process_arguments() {
    if [[ -n "$1" && -n "$2" ]]; then
        provider="$1"
        operation="$2"
    else
        # If insufficient arguments are provided, prompt for them
        echo "Select your cloud provider:"
        echo "1) AWS"
        read -p "Provider (1/1): " provider_choice

        case $provider_choice in
            1) provider="aws" ;;
            *) echo "Invalid option."; exit 1 ;;
        esac

        echo "Select an operation:"
        echo "1) Test"
        echo "2) Setup Scylla"
        echo "3) Configure Scylla Servers"        
        echo "4) Scale-Out"
        echo "5) Scale-In"
        echo "6) Init Load"
        echo "7) Stress Test"
        echo "8) Stepped Stress Test"
        echo "9) Kill all jobs on Loaders"
        echo "10) Destroy"
        read -p "Operation (1 to 10): " operation_choice

        case $operation_choice in
            1) operation="test" ;;
            2) operation="setup" ;;
            3) operation="config" ;;
            4) operation="scaleout" ;;
            5) operation="scalein" ;;
            6) operation="initload" ;;
            7) operation="stresstest" ;;
            8) operation="stepstresstest" ;;
            9) operation="kilload" ;;
            10) operation="destroy" ;;
            *) echo "Invalid operation."; exit 1 ;;
        esac
    fi

    execute_operation
}

execute_operation() {
    if [ "$provider" == "aws" ]; then
        case $operation in
            "test") aws_test ;;
            "setup") aws_setup ;;
            "config") aws_config ;;
            "config") aws_config ;;
            "scaleout") aws_scaleout ;;
            "scalein") aws_scalein ;;
            "initload") aws_initload ;;
            "stresstest") aws_stresstest ;;
            "stepstresstest") aws_stepstresstest ;;
            "kilload") aws_kill_loaders ;;
            "destroy") aws_destroy ;;
            *) echo "Invalid AWS operation."; exit 1 ;;
        esac
    else
        echo "Unsupported provider: $provider"
        exit 1
    fi
}

# Process the provided arguments
process_arguments $1 $2