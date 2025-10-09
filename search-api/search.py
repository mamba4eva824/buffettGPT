import os
from dotenv import load_dotenv
from perplexity import Perplexity

load_dotenv()

client = Perplexity(api_key=os.getenv('buffet_sonar_api'))

search = client.search.create(
    query=[
      "Is Nvidia a recommended stock? Why or why not",
      "What is the current price of Nvidia stock?",
      "What is the market cap of Nvidia?"
    ],
    max_results=5,
    max_tokens_per_page=1024
)

for result in search.results:
    print(f"{result.title}: {result.url}")