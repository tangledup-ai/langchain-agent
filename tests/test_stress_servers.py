#!/usr/bin/env python3
"""
Stress test for server_dashscope.py and server_openai.py

This test measures:
- Maximum concurrent request handling capacity
- Latency metrics (p50, p95, p99, min, max, avg)
- Throughput (requests per second)
- Success/failure rates

Instructions:
1. Start the DashScope server:
   uvicorn fastapi_server.server_dashscope:app --host 0.0.0.0 --port 8588
2. Start the OpenAI server:
   uvicorn fastapi_server.server_openai:app --host 0.0.0.0 --port 8589
3. Set environment variables:
   FAST_AUTH_KEYS=test-key-1,test-key-2
4. Run this test:
   pytest tests/test_stress_servers.py -v
   or
   python tests/test_stress_servers.py [--stream | --no-stream]

    Options:
    --server      Which server to test: dashscope, openai, or both (default: dashscope)
    --stream      Test only streaming endpoints
    --no-stream   Test only non-streaming endpoints
    (no option)   Test only dashscope server, both streaming and non-streaming
"""

import os
import sys
import time
import asyncio
import statistics
import argparse
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from collections import defaultdict
import httpx
from loguru import logger

# Load environment variables (matching test_dashscope_client.py and test_openai_client.py)
from dotenv import load_dotenv

load_dotenv()

# Server URLs (matching test files)
DS_BASE_URL = os.getenv("DS_BASE_URL", "http://127.0.0.1:8588/api/")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8589/v1")

# Normalize base URLs (remove trailing slashes)
DASHSCOPE_BASE_URL = DS_BASE_URL.rstrip("/")
OPENAI_BASE_URL = OPENAI_BASE_URL.rstrip("/")

# API Key (matching test files - use first key if comma-separated)
FAST_AUTH_KEYS = os.getenv("FAST_AUTH_KEYS", "test-key")
API_KEY = FAST_AUTH_KEYS.split(",")[0] if FAST_AUTH_KEYS else "test-key"


@dataclass
class RequestResult:
    """Result of a single request."""

    success: bool
    latency_ms: float
    status_code: Optional[int] = None
    error: Optional[str] = None
    response_size: int = 0


@dataclass
class StressTestResult:
    """Results from a stress test run."""

    server_name: str
    endpoint: str
    concurrency: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    latencies_ms: List[float] = field(default_factory=list)
    throughput_rps: float = 0.0
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if not self.latencies_ms:
            return 0.0
        return statistics.mean(self.latencies_ms)

    @property
    def min_latency_ms(self) -> float:
        """Calculate minimum latency."""
        if not self.latencies_ms:
            return 0.0
        return min(self.latencies_ms)

    @property
    def max_latency_ms(self) -> float:
        """Calculate maximum latency."""
        if not self.latencies_ms:
            return 0.0
        return max(self.latencies_ms)

    @property
    def p50_latency_ms(self) -> float:
        """Calculate 50th percentile latency."""
        if not self.latencies_ms:
            return 0.0
        return statistics.median(self.latencies_ms)

    @property
    def p95_latency_ms(self) -> float:
        """Calculate 95th percentile latency."""
        if not self.latencies_ms:
            return 0.0
        return self._percentile(self.latencies_ms, 95)

    @property
    def p99_latency_ms(self) -> float:
        """Calculate 99th percentile latency."""
        if not self.latencies_ms:
            return 0.0
        return self._percentile(self.latencies_ms, 99)

    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """Calculate percentile value."""
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        if index.is_integer():
            return sorted_data[int(index)]
        lower = sorted_data[int(index)]
        upper = sorted_data[int(index) + 1]
        return lower + (upper - lower) * (index - int(index))


async def make_dashscope_request(
    client: httpx.AsyncClient,
    app_id: str = "test-app",
    session_id: str = "test-session",
    stream: bool = False,
    message: str = "Hello, how are you?",
) -> RequestResult:
    """Make a request to the DashScope server."""
    # Use /api/v1/... if base URL contains /api/, otherwise /v1/...
    # The server supports both endpoints
    if "/api" in DASHSCOPE_BASE_URL:
        url = f"{DASHSCOPE_BASE_URL}/v1/apps/{app_id}/sessions/{session_id}/responses"
    else:
        url = (
            f"{DASHSCOPE_BASE_URL}/api/v1/apps/{app_id}/sessions/{session_id}/responses"
        )
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "input": {
            "session_id": session_id,
            "messages": [{"role": "user", "content": message}],
        },
        "stream": stream,
    }

    start_time = time.perf_counter()
    try:
        if stream:
            response_size = 0
            async with client.stream(
                "POST", url, headers=headers, json=payload, timeout=120.0
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    return RequestResult(
                        success=False,
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        status_code=response.status_code,
                        error=f"HTTP {response.status_code}",
                    )
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        response_size += len(line)
                        # For stress testing, we can stop after receiving first chunk to measure latency
                        # Uncomment the break below if you want to measure time-to-first-byte only
                        # break
        else:
            response = await client.post(
                url, headers=headers, json=payload, timeout=60.0
            )
            response_size = len(response.content)
            if response.status_code != 200:
                return RequestResult(
                    success=False,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    status_code=response.status_code,
                    error=response.text[:200],
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        return RequestResult(
            success=True,
            latency_ms=latency_ms,
            status_code=200,
            response_size=response_size,
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return RequestResult(
            success=False,
            latency_ms=latency_ms,
            error=str(e)[:200],
        )


async def make_openai_request(
    client: httpx.AsyncClient,
    stream: bool = False,
    message: str = "Hello, how are you?",
    thread_id: str = "test-thread",
) -> RequestResult:
    """Make a request to the OpenAI-compatible server."""
    url = f"{OPENAI_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": message}],
        "stream": stream,
        "thread_id": thread_id,
    }

    start_time = time.perf_counter()
    try:
        if stream:
            response_size = 0
            async with client.stream(
                "POST", url, headers=headers, json=payload, timeout=120.0
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    return RequestResult(
                        success=False,
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        status_code=response.status_code,
                        error=f"HTTP {response.status_code}",
                    )
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        response_size += len(line)
                        # For stress testing, we can stop after receiving first chunk to measure latency
                        # Uncomment the break below if you want to measure time-to-first-byte only
                        # break
        else:
            response = await client.post(
                url, headers=headers, json=payload, timeout=60.0
            )
            response_size = len(response.content)
            if response.status_code != 200:
                return RequestResult(
                    success=False,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    status_code=response.status_code,
                    error=response.text[:200],
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        return RequestResult(
            success=True,
            latency_ms=latency_ms,
            status_code=200,
            response_size=response_size,
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return RequestResult(
            success=False,
            latency_ms=latency_ms,
            error=str(e)[:200],
        )


async def run_stress_test(
    request_func,
    server_name: str,
    endpoint: str,
    concurrency: int,
    total_requests: int,
    stream: bool = False,
) -> StressTestResult:
    """Run a stress test with specified concurrency and total requests."""
    logger.info(
        f"Starting stress test: {server_name} - {endpoint} - Concurrency: {concurrency}, Total: {total_requests}, Stream: {stream}"
    )

    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(concurrency)
    results: List[RequestResult] = []

    async def make_request_with_semaphore():
        async with semaphore:
            return await request_func()

    # Create tasks
    tasks = [make_request_with_semaphore() for _ in range(total_requests)]

    # Run all requests concurrently
    start_time = time.perf_counter()
    request_results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = time.perf_counter()

    # Process results
    for result in request_results:
        if isinstance(result, Exception):
            results.append(
                RequestResult(
                    success=False,
                    latency_ms=0.0,
                    error=str(result)[:200],
                )
            )
        else:
            results.append(result)

    # Calculate metrics
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    latencies = [r.latency_ms for r in successful]

    duration = end_time - start_time
    throughput = len(successful) / duration if duration > 0 else 0

    return StressTestResult(
        server_name=server_name,
        endpoint=endpoint,
        concurrency=concurrency,
        total_requests=total_requests,
        successful_requests=len(successful),
        failed_requests=len(failed),
        latencies_ms=latencies,
        throughput_rps=throughput,
        duration_seconds=duration,
    )


def print_results(result: StressTestResult):
    """Print formatted stress test results."""
    print(f"\n{'=' * 80}")
    print(f"STRESS TEST RESULTS: {result.server_name}")
    print(f"{'=' * 80}")
    print(f"Endpoint:              {result.endpoint}")
    print(f"Concurrency:            {result.concurrency}")
    print(f"Total Requests:         {result.total_requests}")
    print(
        f"Successful:             {result.successful_requests} ({result.success_rate:.2f}%)"
    )
    print(f"Failed:                 {result.failed_requests}")
    print(f"Duration:               {result.duration_seconds:.3f}s")
    print(f"Throughput:             {result.throughput_rps:.2f} req/s")
    print(f"\nLatency Metrics (ms):")
    print(f"  Min:                  {result.min_latency_ms:.2f}")
    print(f"  Max:                  {result.max_latency_ms:.2f}")
    print(f"  Average:              {result.avg_latency_ms:.2f}")
    print(f"  Median (p50):         {result.p50_latency_ms:.2f}")
    print(f"  p95:                  {result.p95_latency_ms:.2f}")
    print(f"  p99:                  {result.p99_latency_ms:.2f}")

    if result.failed_requests > 0:
        print(f"\nErrors encountered: {result.failed_requests}")
    print(f"{'=' * 80}\n")


async def test_dashscope_server(stream_mode: Optional[bool] = None):
    """Test the DashScope server with various concurrency levels.

    Args:
        stream_mode: If True, test only streaming. If False, test only non-streaming.
                     If None, test both.
    """
    print("\n" + "=" * 80)
    print("TESTING DASHSCOPE SERVER")
    if stream_mode is True:
        print("Mode: Streaming only")
    elif stream_mode is False:
        print("Mode: Non-streaming only")
    else:
        print("Mode: Both streaming and non-streaming")
    print("=" * 80)

    # Test configurations: (concurrency, total_requests, stream)
    all_test_configs = [
        (1, 10, False),  # Sequential, non-streaming
        (5, 25, False),  # Low concurrency
        (10, 50, False),  # Medium concurrency
        (20, 100, False),  # High concurrency
        (50, 200, False),  # Very high concurrency
        (1, 10, True),  # Sequential, streaming
        (10, 50, True),  # Medium concurrency, streaming
        (20, 100, True),  # High concurrency, streaming
    ]

    # Filter based on stream_mode
    if stream_mode is not None:
        test_configs = [cfg for cfg in all_test_configs if cfg[2] == stream_mode]
    else:
        test_configs = all_test_configs

    all_results = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        for concurrency, total_requests, stream in test_configs:
            endpoint = f"/v1/apps/{{app_id}}/sessions/{{session_id}}/responses"
            if stream:
                endpoint += " (streaming)"

            # Create request function with client bound
            async def request_func():
                # Overall server capacity across many sessions:
                # use a unique session_id (thread_id) per request to avoid per-thread contention
                session_id = str(uuid.uuid4())
                return await make_dashscope_request(
                    client,
                    app_id=f"test-app-{concurrency}",
                    session_id=session_id,
                    stream=stream,
                    message=f"Test message for concurrency {concurrency}",
                )

            result = await run_stress_test(
                request_func,
                "DashScope Server",
                endpoint,
                concurrency,
                total_requests,
                stream,
            )

            all_results.append(result)
            print_results(result)

            # Small delay between test runs
            await asyncio.sleep(1)

    return all_results


async def test_openai_server(stream_mode: Optional[bool] = None):
    """Test the OpenAI-compatible server with various concurrency levels.

    Args:
        stream_mode: If True, test only streaming. If False, test only non-streaming.
                     If None, test both.
    """
    print("\n" + "=" * 80)
    print("TESTING OPENAI SERVER")
    if stream_mode is True:
        print("Mode: Streaming only")
    elif stream_mode is False:
        print("Mode: Non-streaming only")
    else:
        print("Mode: Both streaming and non-streaming")
    print("=" * 80)

    # Test configurations: (concurrency, total_requests, stream)
    all_test_configs = [
        (1, 10, False),  # Sequential, non-streaming
        (5, 25, False),  # Low concurrency
        (10, 50, False),  # Medium concurrency
        (20, 100, False),  # High concurrency
        (50, 200, False),  # Very high concurrency
        (1, 10, True),  # Sequential, streaming
        (10, 50, True),  # Medium concurrency, streaming
        (20, 100, True),  # High concurrency, streaming
    ]

    # Filter based on stream_mode
    if stream_mode is not None:
        test_configs = [cfg for cfg in all_test_configs if cfg[2] == stream_mode]
    else:
        test_configs = all_test_configs

    all_results = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        for concurrency, total_requests, stream in test_configs:
            endpoint = "/v1/chat/completions"
            if stream:
                endpoint += " (streaming)"

            # Create request function with client bound
            async def request_func():
                # Overall server capacity across many sessions:
                # use a unique thread_id per request to avoid per-thread contention
                thread_id = str(uuid.uuid4())
                return await make_openai_request(
                    client,
                    stream=stream,
                    message=f"Test message for concurrency {concurrency}",
                    thread_id=thread_id,
                )

            result = await run_stress_test(
                request_func,
                "OpenAI Server",
                endpoint,
                concurrency,
                total_requests,
                stream,
            )

            all_results.append(result)
            print_results(result)

            # Small delay between test runs
            await asyncio.sleep(1)

    return all_results


def print_summary(results: List[StressTestResult], header: str):
    """Print a summary of test results for a single experiment.

    Args:
        results: List of stress test results
        header: Header text to print for this experiment
    """
    print("\n" + "=" * 80)
    print(header)
    print("=" * 80)

    # Separate streaming and non-streaming results
    streaming_results = [r for r in results if "streaming" in r.endpoint]
    non_streaming_results = [r for r in results if "streaming" not in r.endpoint]

    # Print non-streaming results if available
    if non_streaming_results:
        print("\nNon-Streaming:")
        print(
            f"{'Concurrency':<15} {'Requests':<12} {'Success %':<12} {'Throughput (req/s)':<20} {'Avg Latency (ms)':<18} {'p95 (ms)':<12} {'p99 (ms)':<12}"
        )
        print("-" * 110)
        for result in non_streaming_results:
            print(
                f"{result.concurrency:<15} {result.total_requests:<12} {result.success_rate:<11.2f}% "
                f"{result.throughput_rps:<20.2f} {result.avg_latency_ms:<18.2f} "
                f"{result.p95_latency_ms:<12.2f} {result.p99_latency_ms:<12.2f}"
            )

    # Print streaming results if available
    if streaming_results:
        print("\nStreaming:")
        print(
            f"{'Concurrency':<15} {'Requests':<12} {'Success %':<12} {'Throughput (req/s)':<20} {'Avg Latency (ms)':<18} {'p95 (ms)':<12} {'p99 (ms)':<12}"
        )
        print("-" * 110)
        for result in streaming_results:
            print(
                f"{result.concurrency:<15} {result.total_requests:<12} {result.success_rate:<11.2f}% "
                f"{result.throughput_rps:<20.2f} {result.avg_latency_ms:<18.2f} "
                f"{result.p95_latency_ms:<12.2f} {result.p99_latency_ms:<12.2f}"
            )

    print("\n" + "=" * 80)


async def main(stream_mode: Optional[bool] = None, server: str = "dashscope"):
    """Main function to run all stress tests.

    Args:
        stream_mode: If True, test only streaming. If False, test only non-streaming.
                     If None, test both.
        server: Which server(s) to test: "dashscope", "openai", or "both".
    """
    print("\n" + "=" * 80)
    print("STRESS TEST FOR FASTAPI SERVERS")
    print("=" * 80)
    print(f"Server(s) to test: {server}")
    print(f"DashScope Server URL: {DS_BASE_URL}")
    print(f"OpenAI Server URL: {OPENAI_BASE_URL}")
    print(f"API Key: {API_KEY[:8]}..." if len(API_KEY) > 8 else f"API Key: {API_KEY}")
    if stream_mode is True:
        print("Testing Mode: Streaming only")
    elif stream_mode is False:
        print("Testing Mode: Non-streaming only")
    else:
        print("Testing Mode: Both streaming and non-streaming")
    print("=" * 80)

    # Check if servers are reachable
    async with httpx.AsyncClient(timeout=5.0) as client:
        if server in ("dashscope", "both"):
            try:
                # Health endpoint is at root, not under /api/
                # Extract base URL without /api/ path
                if "/api" in DASHSCOPE_BASE_URL:
                    base_without_api = DASHSCOPE_BASE_URL.split("/api")[0]
                else:
                    base_without_api = DASHSCOPE_BASE_URL.rstrip("/")
                response = await client.get(f"{base_without_api}/health")
                if response.status_code != 200:
                    logger.warning(
                        f"DashScope server health check failed: {response.status_code}"
                    )
            except Exception as e:
                logger.error(
                    f"Cannot reach DashScope server at {DASHSCOPE_BASE_URL}: {e}"
                )
                logger.info(
                    "Please start the server: uvicorn fastapi_server.server_dashscope:app --host 0.0.0.0 --port 8588"
                )

        if server in ("openai", "both"):
            try:
                response = await client.get(f"{OPENAI_BASE_URL}/health")
                if response.status_code != 200:
                    logger.warning(
                        f"OpenAI server health check failed: {response.status_code}"
                    )
            except Exception as e:
                logger.error(f"Cannot reach OpenAI server at {OPENAI_BASE_URL}: {e}")
                logger.info(
                    "Please start the server: uvicorn fastapi_server.server_openai:app --host 0.0.0.0 --port 8589"
                )

    # Run stress tests
    if server in ("dashscope", "both"):
        dashscope_results = await test_dashscope_server(stream_mode)
        print_summary(dashscope_results, "DASHSCOPE SERVER SUMMARY")

    if server in ("openai", "both"):
        openai_results = await test_openai_server(stream_mode)
        print_summary(openai_results, "OPENAI SERVER SUMMARY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stress test for FastAPI servers (DashScope and OpenAI compatible)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/test_stress_servers.py                  # Test only dashscope, both streaming modes
  python tests/test_stress_servers.py --server dashscope  # Same as default
  python tests/test_stress_servers.py --server openai     # Test only openai server
  python tests/test_stress_servers.py --server both        # Test both servers
  python tests/test_stress_servers.py --stream         # Test only streaming endpoints
  python tests/test_stress_servers.py --no-stream      # Test only non-streaming endpoints
        """,
    )
    parser.add_argument(
        "--server",
        choices=["dashscope", "openai", "both"],
        default="dashscope",
        help="Which server to test: dashscope (default), openai, or both",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--stream", action="store_true", help="Test only streaming endpoints"
    )
    group.add_argument(
        "--no-stream",
        action="store_true",
        dest="no_stream",
        help="Test only non-streaming endpoints",
    )

    args = parser.parse_args()

    # Determine stream_mode from arguments
    if args.stream:
        stream_mode = True
    elif args.no_stream:
        stream_mode = False
    else:
        stream_mode = None  # Test both

    asyncio.run(main(stream_mode, args.server))
