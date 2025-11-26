import os
from dotenv import load_dotenv

load_dotenv()

from perplexity import Perplexity

# Initialize the client (uses PERPLEXITY_API_KEY environment variable)
client = Perplexity(api_key=os.getenv('buffet_sonar_api'))

# Make the streaming API call
stream = client.chat.completions.create(
    model="sonar",
    messages=[{"role": "user", "content": "What is the cashflow earnings of Nvidia over the last 10 years annually. Can you provide a matrix for each year regarding those metrics to visualize the growth with a table?"}],
    search_mode="sec",
    search_after_date_filter="1/1/2015",
    stream=True
)

# Process the streaming response
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")