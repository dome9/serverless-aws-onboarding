import json

print('Loading function')


def lambda_handler(event, context):
	print("Received event: " + json.dumps(event, indent=2))
	return event  # Echo back the first key value
	#raise Exception('Something went wrong')
