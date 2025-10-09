import os
import time
from dotenv import load_dotenv
from perplexity import Perplexity

load_dotenv()

# Pricing per 1M tokens (input/output)
PRICING = {
    "sonar": {"input": 1.00, "output": 1.00},
    "sonar-pro": {"input": 3.00, "output": 15.00},
    "sonar-reasoning": {"input": 5.00, "output": 5.00},
    "sonar-deep-research": {"input": 10.00, "output": 8.00},
}

MODELS = ["sonar", "sonar-pro"]

# Test query
TEST_QUERY = "What is the cashflow earnings of Nvidia over the last 10 years annually. Can you provide a matrix for each year regarding those metrics to visualize the growth with a table?"

def test_model(client, model_name):
    """Test a single model and collect metrics."""
    print(f"\n{'='*80}")
    print(f"Testing model: {model_name}")
    print(f"{'='*80}\n")

    start_time = time.time()
    first_token_time = None
    full_response = ""
    input_tokens = 0
    output_tokens = 0

    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": TEST_QUERY}],
            search_mode="sec",
            search_after_date_filter="1/1/2015",
            stream=True
        )

        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.time()

            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                print(content, end="", flush=True)

            # Track token usage if available
            if hasattr(chunk, 'usage') and chunk.usage:
                if hasattr(chunk.usage, 'prompt_tokens'):
                    input_tokens = chunk.usage.prompt_tokens
                if hasattr(chunk.usage, 'completion_tokens'):
                    output_tokens = chunk.usage.completion_tokens

        end_time = time.time()
        print("\n")

        # Estimate tokens if not provided (rough approximation: 1 token ≈ 4 chars)
        if output_tokens == 0:
            output_tokens = len(full_response) // 4
        if input_tokens == 0:
            input_tokens = len(TEST_QUERY) // 4

        return {
            "model": model_name,
            "total_time": end_time - start_time,
            "time_to_first_token": (first_token_time - start_time) if first_token_time else 0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "response_length": len(full_response),
            "success": True
        }

    except Exception as e:
        print(f"\nError testing {model_name}: {str(e)}\n")
        return {
            "model": model_name,
            "total_time": 0,
            "time_to_first_token": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "response_length": 0,
            "success": False,
            "error": str(e)
        }

def calculate_cost_per_1000(metrics):
    """Calculate cost for 1000 queries based on token usage."""
    model = metrics["model"]
    if not metrics["success"]:
        return {"cost_per_1000": 0, "input_cost": 0, "output_cost": 0}

    pricing = PRICING.get(model, {"input": 0, "output": 0})

    # Cost per single query
    input_cost_per_query = (metrics["input_tokens"] / 1_000_000) * pricing["input"]
    output_cost_per_query = (metrics["output_tokens"] / 1_000_000) * pricing["output"]

    # Cost for 1000 queries
    input_cost_1000 = input_cost_per_query * 1000
    output_cost_1000 = output_cost_per_query * 1000
    total_cost_1000 = input_cost_1000 + output_cost_1000

    return {
        "cost_per_1000": total_cost_1000,
        "input_cost": input_cost_1000,
        "output_cost": output_cost_1000
    }

def print_comparison_table(results):
    """Print a formatted comparison table."""
    print("\n" + "="*120)
    print("MODEL COMPARISON RESULTS")
    print("="*120)

    # Headers
    headers = ["Model", "Status", "Total Time (s)", "TTFT (s)", "Input Tokens", "Output Tokens",
               "Response Length", "Cost/1000 Queries"]

    # Print header
    print(f"\n{headers[0]:<20} {headers[1]:<10} {headers[2]:<15} {headers[3]:<12} {headers[4]:<15} "
          f"{headers[5]:<15} {headers[6]:<18} {headers[7]:<20}")
    print("-" * 120)

    # Print each model's results
    for result in results:
        status = "✓ Success" if result["success"] else "✗ Failed"
        cost_info = calculate_cost_per_1000(result)
        cost_str = f"${cost_info['cost_per_1000']:.4f}" if result["success"] else "N/A"

        print(f"{result['model']:<20} {status:<10} {result['total_time']:<15.2f} "
              f"{result['time_to_first_token']:<12.2f} {result['input_tokens']:<15} "
              f"{result['output_tokens']:<15} {result['response_length']:<18} {cost_str:<20}")

    print("-" * 120)

    # Print detailed cost breakdown
    print("\nDETAILED COST BREAKDOWN (for 1000 queries):")
    print("-" * 120)
    for result in results:
        if result["success"]:
            cost_info = calculate_cost_per_1000(result)
            print(f"\n{result['model']}:")
            print(f"  Input Cost:  ${cost_info['input_cost']:.4f}")
            print(f"  Output Cost: ${cost_info['output_cost']:.4f}")
            print(f"  Total Cost:  ${cost_info['cost_per_1000']:.4f}")

    print("\n" + "="*120)

def main():
    # Initialize the client
    api_key = os.getenv('buffet_sonar_api')
    if not api_key:
        print("Error: buffet_sonar_api environment variable not set")
        return

    client = Perplexity(api_key=api_key)

    results = []

    # Test each model
    for model in MODELS:
        result = test_model(client, model)
        results.append(result)
        time.sleep(1)  # Small delay between tests

    # Print comparison table
    print_comparison_table(results)

if __name__ == "__main__":
    main()
