import asyncio
import aiohttp
import time
import random
import statistics
from datetime import datetime

# Your app URL
BASE_URL = "http://localhost:5000"
SESSION_TOKENS = ["a5Z6nj-SQvWJPDynC__da1XB3jVf1Y9uONSlAX70ZSg"]  # Your actual session token

class LoadTester:
    def __init__(self, base_url, session_tokens):
        self.base_url = base_url
        self.session_tokens = session_tokens
        self.results = []

    async def send_chat_request(self, session, user_id, message):
        """Send a single chat request"""
        start_time = time.time()
        response_time = None
        status_code = 0

        try:
            headers = {
                "Authorization": f"Bearer {self.session_tokens[user_id % len(self.session_tokens)]}",
                "Content-Type": "application/json"
            }
            data = {"data": message}

            async with session.post(f"{self.base_url}/data", json=data, headers=headers) as response:
                response_time = time.time() - start_time

                # Try to parse JSON response
                try:
                    result = await response.json()
                    print(f"User {user_id}: HTTP {response.status} in {response_time:.2f}s - Response: {result}")
                except:
                    text_result = await response.text()
                    print(f"User {user_id}: HTTP {response.status} in {response_time:.2f}s - Response: {text_result[:100]}...")

                return {
                    "user_id": user_id,
                    "response_time": response_time,
                    "status_code": response.status,
                    "success": response.status == 200,
                    "timestamp": datetime.now()
                }

        except aiohttp.ClientError as e:
            response_time = time.time() - start_time if response_time is None else response_time
            print(f"User {user_id}: Client Error - {e}")
            return {
                "user_id": user_id,
                "response_time": response_time,
                "status_code": 0,
                "success": False,
                "error": str(e),
                "timestamp": datetime.now()
            }
        except Exception as e:
            response_time = time.time() - start_time if response_time is None else response_time
            print(f"User {user_id}: Unexpected Error - {e}")
            return {
                "user_id": user_id,
                "response_time": response_time,
                "status_code": 0,
                "success": False,
                "error": str(e),
                "timestamp": datetime.now()
            }

    async def run_single_test(self, num_users, messages_per_user, think_time=0):
        """Run a single load test scenario"""
        print(f"\n🚀 Starting load test: {num_users} users, {messages_per_user} messages each")
        print("=" * 60)

        # Configure session with timeout
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = []
            test_messages = [
                "I want to visit Paris",
                "My departure city is London",
                "What's the weather like?",
                "Find me cheap flights",
                "Search hotels for 2 guests",
                "I need a rental car",
                "Show me tourist attractions",
                "Book a restaurant reservation",
                "What's the local currency?",
                "Find beach resorts"
            ]

            # Create tasks for all users
            for user_id in range(num_users):
                for msg_num in range(messages_per_user):
                    message = random.choice(test_messages)
                    task = self.send_chat_request(session, user_id, message)
                    tasks.append(task)

                    # Add think time between messages for same user
                    if think_time > 0 and msg_num < messages_per_user - 1:
                        tasks.append(asyncio.sleep(think_time))

            # Run all requests
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time

            # Process results
            successful_requests = []
            failed_requests = []

            for result in results:
                if isinstance(result, Exception):
                    failed_requests.append({
                        "error": str(result),
                        "success": False,
                        "response_time": 0
                    })
                elif isinstance(result, dict):
                    if result.get("success"):
                        successful_requests.append(result)
                    else:
                        failed_requests.append(result)

            # Calculate statistics
            response_times = [r["response_time"] for r in successful_requests if r["response_time"] is not None]

            test_result = {
                "scenario": f"{num_users} users × {messages_per_user} messages",
                "total_requests": len(tasks),
                "successful_requests": len(successful_requests),
                "failed_requests": len(failed_requests),
                "success_rate": len(successful_requests) / len(tasks) * 100,
                "total_time": total_time,
                "avg_response_time": statistics.mean(response_times) if response_times else 0,
                "min_response_time": min(response_times) if response_times else 0,
                "max_response_time": max(response_times) if response_times else 0,
                "requests_per_second": len(tasks) / total_time if total_time > 0 else 0,
                "timestamp": datetime.now()
            }

            self.results.append(test_result)
            self.print_results(test_result)
            return test_result

    def print_results(self, result):
        """Print formatted results"""
        print(f"\n📊 LOAD TEST RESULTS:")
        print(f"Scenario: {result['scenario']}")
        print(f"Total Requests: {result['total_requests']}")
        print(f"Successful: {result['successful_requests']}")
        print(f"Failed: {result['failed_requests']}")
        print(f"Success Rate: {result['success_rate']:.1f}%")
        print(f"Total Time: {result['total_time']:.2f}s")
        print(f"Avg Response Time: {result['avg_response_time']:.2f}s")
        print(f"Min Response Time: {result['min_response_time']:.2f}s")
        print(f"Max Response Time: {result['max_response_time']:.2f}s")
        print(f"Requests/Second: {result['requests_per_second']:.2f}")

    async def run_comprehensive_test(self):
        """Run multiple test scenarios"""
        print("🔧 Starting Comprehensive Load Testing")
        print("=" * 60)

        # Test scenarios: (num_users, messages_per_user, think_time)
        test_scenarios = [
            (5, 2, 1),    # Light load
            (10, 3, 0.5), # Medium load
            (20, 2, 0.2), # Heavy load
            (30, 2, 0.1), # Stress test
        ]

        for num_users, messages_per_user, think_time in test_scenarios:
            await self.run_single_test(num_users, messages_per_user, think_time)
            print("\n" + "="*60)
            await asyncio.sleep(2)  # Cool down between tests

    def generate_report(self):
        """Generate a summary report"""
        print(f"\n📈 LOAD TESTING SUMMARY REPORT")
        print("=" * 60)
        print(f"Generated at: {datetime.now()}")
        print(f"Base URL: {BASE_URL}")
        print(f"Total Test Scenarios: {len(self.results)}")
        print("\n" + "="*60)

        for i, result in enumerate(self.results, 1):
            print(f"\nScenario {i}: {result['scenario']}")
            print(f"  Success Rate: {result['success_rate']:.1f}%")
            print(f"  Avg Response Time: {result['avg_response_time']:.2f}s")
            print(f"  Throughput: {result['requests_per_second']:.2f} req/s")

async def main():
    """Main function to run load tests"""
    print("🚀 Starting AI Assistant Load Testing")
    print(f"Target URL: {BASE_URL}")
    print(f"Available Tokens: {len(SESSION_TOKENS)}")

    # Validate the server is reachable
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL, timeout=10) as response:
                print(f"✅ Server is reachable - Status: {response.status}")
    except Exception as e:
        print(f"❌ Cannot reach server: {e}")
        return

    # Initialize load tester
    tester = LoadTester(BASE_URL, SESSION_TOKENS)

    # Run comprehensive tests
    await tester.run_comprehensive_test()

    # Generate final report
    tester.generate_report()

if __name__ == "__main__":
    # Run the load tests
    asyncio.run(main())
