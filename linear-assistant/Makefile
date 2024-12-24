.PHONY: test-post-curl
test-post-curl:
	curl -X POST http://localhost:8000/webhook/new-email-thread \
		-H "Content-Type: application/json" \
		-d '{"from_address": "test@example.com", \
			"to_address": "support@company.com", \
			"subject": "New Ticket", \
			"body": "Can you make a new issue for Austin to restock the fridges with tasty beers?", \
			"message_id": "test123", \
			"previous_thread": [], \
			"raw_email": "raw email content" \
			}'
