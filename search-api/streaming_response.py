import os
from dotenv import load_dotenv

load_dotenv()

from perplexity import Perplexity

# Initialize the client (uses PERPLEXITY_API_KEY environment variable)
client = Perplexity(api_key=os.getenv('buffet_sonar_api'))

# Make the streaming API call
stream = client.chat.completions.create(
    model="sonar",
    messages=[
        {"role": "user", "content": "What are the most popular open-source alternatives to OpenAI's GPT models?"}
    ],
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")