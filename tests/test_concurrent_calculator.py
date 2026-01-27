#!/usr/bin/env python3
"""
Concurrent calculator test for DashScope Application.call against server_dashscope.py

Tests the agent's performance when handling multiple calculator requests concurrently
with different session IDs.

Instructions:
- Start the DashScope-compatible server first:
    uvicorn fastapi_server.server_dashscope:app --host 0.0.0.0 --port 8588 --reload
- Run this script to test concurrent performance
"""
import os
import uuid
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv
from loguru import logger
from http import HTTPStatus

load_dotenv()

try:
    from dashscope import Application
    import dashscope
except Exception as e:
    print("dashscope package not found. Please install it: pip install dashscope")
    raise

# <<< Paste your running FastAPI base url here >>>
BASE_URL = os.getenv("DS_BASE_URL", "http://127.0.0.1:8588/api/")

# Params
API_KEY = os.getenv("ALI_API_KEY", "test-key")
APP_ID = os.getenv("ALI_APP_ID", "test-app")

# Different equations to calculate
EQUATIONS = [
    "1234 * 5641",
    "9876 + 5432 * 2",
    "100000 / 256",
    "2 ** 20",
    "123456 - 78901",
    "999 * 999",
    "314159 / 100",
    "42 ** 3",
]


@dataclass
class RequestResult:
    session_id: str
    equation: str
    response_text: str
    duration_seconds: float
    success: bool
    error: Optional[str] = None


def make_request(equation: str, session_id: str, stream: bool = True) -> RequestResult:
    """Make a single calculator request and return the result with timing."""
    dialogue = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"use calculator to calculate {equation}"},
    ]

    call_params = {
        "api_key": API_KEY,
        "app_id": APP_ID,
        "session_id": session_id,
        "messages": dialogue,
        "stream": stream,
    }

    start_time = time.perf_counter()
    
    try:
        responses = Application.call(**call_params)
        
        if stream:
            last_text = ""
            final_text = ""
            for resp in responses:
                if resp.status_code != HTTPStatus.OK:
                    raise Exception(f"Error: code={resp.status_code}, message={resp.message}")
                current_text = getattr(getattr(resp, "output", None), "text", None)
                if current_text is None:
                    continue
                if len(current_text) >= len(last_text):
                    delta = current_text[len(last_text):]
                else:
                    delta = current_text
                if delta:
                    final_text = current_text
                last_text = current_text
            response_text = final_text
        else:
            if responses.status_code != HTTPStatus.OK:
                raise Exception(f"Error: code={responses.status_code}, message={responses.message}")
            response_text = getattr(getattr(responses, "output", None), "text", "")
        
        duration = time.perf_counter() - start_time
        return RequestResult(
            session_id=session_id,
            equation=equation,
            response_text=response_text,
            duration_seconds=duration,
            success=True,
        )
    except Exception as e:
        duration = time.perf_counter() - start_time
        return RequestResult(
            session_id=session_id,
            equation=equation,
            response_text="",
            duration_seconds=duration,
            success=False,
            error=str(e),
        )


def run_concurrent_test(equations: list[str], max_workers: int) -> list[RequestResult]:
    """Run multiple calculator requests concurrently with specified worker count."""
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for eq in equations:
            session_id = str(uuid.uuid4())
            future = executor.submit(make_request, eq, session_id)
            futures[future] = eq
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    
    return results


def print_results(results: list[RequestResult], concurrency: int):
    """Print formatted results for a test run."""
    print(f"\n{'='*70}")
    print(f"CONCURRENCY LEVEL: {concurrency}")
    print(f"{'='*70}")
    
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    total_duration = sum(r.duration_seconds for r in results)
    avg_duration = total_duration / len(results) if results else 0
    max_duration = max(r.duration_seconds for r in results) if results else 0
    min_duration = min(r.duration_seconds for r in results) if results else 0
    
    print(f"\nSummary:")
    print(f"  Total requests:    {len(results)}")
    print(f"  Successful:        {len(successful)}")
    print(f"  Failed:            {len(failed)}")
    print(f"  Avg duration:      {avg_duration:.3f}s")
    print(f"  Min duration:      {min_duration:.3f}s")
    print(f"  Max duration:      {max_duration:.3f}s")
    print(f"  Total time (wall): {max_duration:.3f}s (limited by slowest)")
    
    print(f"\nDetailed Results:")
    print(f"  {'Equation':<25} {'Duration':<12} {'Status':<10} {'Session ID (first 8)'}")
    print(f"  {'-'*25} {'-'*12} {'-'*10} {'-'*20}")
    
    for r in sorted(results, key=lambda x: x.duration_seconds):
        status = "✓ OK" if r.success else "✗ FAIL"
        print(f"  {r.equation:<25} {r.duration_seconds:>8.3f}s   {status:<10} {r.session_id[:8]}")
        if not r.success:
            print(f"    Error: {r.error}")
    
    if successful:
        print(f"\nSample Response (first successful):")
        sample = successful[0]
        response_preview = sample.response_text[:200] + "..." if len(sample.response_text) > 200 else sample.response_text
        print(f"  Equation: {sample.equation}")
        print(f"  Response: {response_preview}")


def main():
    # Point the SDK to our FastAPI implementation
    if BASE_URL and ("/api/" in BASE_URL):
        dashscope.base_http_api_url = BASE_URL
    print(f"Using base_http_api_url = {dashscope.base_http_api_url}")
    
    # Test with different concurrency levels
    concurrency_levels = [1, 2, 4, 8]
    
    # Use first 2 equations for basic test, then more for higher concurrency
    test_configs = [
        (1, EQUATIONS[:2]),    # Sequential: 2 equations
        (2, EQUATIONS[:2]),    # 2 concurrent: 2 equations
        (4, EQUATIONS[:4]),    # 4 concurrent: 4 equations
        (8, EQUATIONS[:8]),    # 8 concurrent: 8 equations
    ]
    
    all_results = {}
    overall_start = time.perf_counter()
    
    for concurrency, equations in test_configs:
        print(f"\n>>> Running test with concurrency={concurrency}, equations={len(equations)}")
        test_start = time.perf_counter()
        results = run_concurrent_test(equations, max_workers=concurrency)
        test_duration = time.perf_counter() - test_start
        all_results[concurrency] = {
            "results": results,
            "wall_time": test_duration,
        }
        print_results(results, concurrency)
        print(f"\n  Wall clock time for this test: {test_duration:.3f}s")
    
    overall_duration = time.perf_counter() - overall_start
    
    # Final comparison
    print(f"\n{'='*70}")
    print("CONCURRENCY COMPARISON")
    print(f"{'='*70}")
    print(f"  {'Concurrency':<15} {'Requests':<12} {'Wall Time':<15} {'Throughput'}")
    print(f"  {'-'*15} {'-'*12} {'-'*15} {'-'*20}")
    
    for concurrency, data in all_results.items():
        num_requests = len(data["results"])
        wall_time = data["wall_time"]
        throughput = num_requests / wall_time if wall_time > 0 else 0
        print(f"  {concurrency:<15} {num_requests:<12} {wall_time:<15.3f} {throughput:.2f} req/s")
    
    print(f"\nTotal test duration: {overall_duration:.3f}s")


if __name__ == "__main__":
    main()
























