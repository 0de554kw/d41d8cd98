The script is crawling for JIRA url and collect worklog entries of specified user or all users in the specified project
Parse the entries and accumulate spent hours for every user per day, and sum of all reported hours per month.

The script uses a json config

{
  "username": "User Name",
  
  "password": "Password",
  
  "project": "Project name",
  
  "jira_url": "https://jira[.]com Url for target JIRA instance",
  
  "jql": "Custom JIRA query line can be specified here"
  
  "max_results": 1000
}

Since the config contain sensitive data, it should be stored accordingly. 
