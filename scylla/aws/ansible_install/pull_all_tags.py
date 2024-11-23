import requests

# Faisal: This simple script is used to pull all the available scylla-monotiring builds from the git repo. IT appears that 4.7 onwards, the semantics are not correct
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

# Example usage
owner = "scylladb"
repo = "scylla-monitoring"
all_tags = get_all_tags(owner, repo)

print("All tags in the repository:")
for tag in all_tags:
    print(tag)
