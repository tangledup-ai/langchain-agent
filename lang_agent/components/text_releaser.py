import time
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Iterator, AsyncIterator, Any, List, Tuple, Optional
from collections import deque


@dataclass
class ReleaseState:
    """Mutable state for the release process."""
    read_idx: int = 0
    yield_idx: int = 0
    in_delay_mode: bool = False
    start_key_search_pos: int = 0
    end_key_search_pos: int = 0
    found_start_keys: List[Tuple[int, int]] = field(default_factory=list)
    found_end_keys: List[Tuple[int, int]] = field(default_factory=list)


class TextReleaser:
    """
    Controls the release rate of streaming text chunks based on special key markers.
    
    This class consumes a text stream and yields chunks with controlled timing:
    - Before start_key: yields chunks immediately as they arrive
    - After start_key: yields chunks with a delay (WAIT_TIME) between each
    - When end_key appears: skips all pending delayed chunks and resumes immediately after end_key
    - Both start_key and end_key are filtered out and never yielded
    
    Keys can span multiple chunks (e.g., "[CHAT", "TY_OUT]") and are detected across boundaries.
    Keys always start with "[" character, allowing the class to buffer potential key prefixes.
    
    Example flow:
        Input:  ["Hello ", "[CHATTY_OUT]", "Thinking...", "[TOOL_OUT]", " Result: 42"]
        Output: ["Hello "] -> delay -> ["Thinking..."] -> skip to -> [" Result: 42"]
    """
    KEY_START_CHAR = "["

    def __init__(self, start_key: str = None, end_key: str = None, wait_time:float=0.15):
        """
        Initialize the TextReleaser.
        
        Args:
            start_key: Marker that triggers delayed yielding (e.g., "[CHATTY_OUT]")
            end_key: Marker that ends delayed yielding and skips pending chunks (e.g., "[TOOL_OUT]")
        """
        self.start_key = start_key
        self.end_key = end_key
        self.WAIT_TIME = wait_time  # sec/word in chinese

        # Internal state for producer-consumer pattern
        self._buffer: deque = deque()  # stores (chunk, chunk_start_pos, chunk_end_pos)
        self._lock = threading.Lock()
        self._producer_done = threading.Event()
        self._accumulated_text = ""  # full text accumulated so far for key detection

    def _is_prefix_of_key(self, text: str) -> bool:
        """Check if text is a prefix of start_key or end_key."""
        if self.start_key and self.start_key.startswith(text):
            return True
        if self.end_key and self.end_key.startswith(text):
            return True
        return False

    def _find_key_range(self, key: str, after_pos: int = 0) -> Optional[Tuple[int, int]]:
        """Find the start and end position of a key in accumulated text after given position."""
        if not key:
            return None
        idx = self._accumulated_text.find(key, after_pos)
        if idx == -1:
            return None
        return (idx, idx + len(key))

    def _producer(self, text_iterator: Iterator[Any]):
        """Consumes text_iterator and stores chunks into buffer as they arrive."""
        for chunk in text_iterator:
            with self._lock:
                if isinstance(chunk, str):
                    start_pos = len(self._accumulated_text)
                    self._accumulated_text += chunk
                    end_pos = len(self._accumulated_text)
                    self._buffer.append((chunk, start_pos, end_pos))
                else:
                    self._buffer.append((chunk, None, None))
        self._producer_done.set()

    def _chunk_overlaps_range(self, chunk_start: int, chunk_end: int, range_start: int, range_end: int) -> bool:
        """Check if chunk overlaps with a given range."""
        return not (chunk_end <= range_start or chunk_start >= range_end)

    def _search_for_keys(self, state: ReleaseState, accumulated_len: int) -> None:
        """Search for complete start_key and end_key occurrences in accumulated text."""
        # Search for start_keys
        while True:
            key_range = self._find_key_range(self.start_key, state.start_key_search_pos)
            if key_range and key_range[1] <= accumulated_len:
                state.found_start_keys.append(key_range)
                state.start_key_search_pos = key_range[1]
            else:
                break

        # Search for end_keys
        while True:
            key_range = self._find_key_range(self.end_key, state.end_key_search_pos)
            if key_range and key_range[1] <= accumulated_len:
                state.found_end_keys.append(key_range)
                state.end_key_search_pos = key_range[1]
            else:
                break

    def _find_potential_key_position(self, accumulated: str) -> int:
        """Find position of potential incomplete key at end of accumulated text. Returns -1 if none."""
        max_key_len = max(len(self.start_key or ""), len(self.end_key or ""))
        for search_start in range(max(0, len(accumulated) - max_key_len + 1), len(accumulated)):
            suffix = accumulated[search_start:]
            if suffix.startswith(self.KEY_START_CHAR) and self._is_prefix_of_key(suffix):
                return search_start
        return -1

    def _get_safe_end_pos(self, accumulated: str, producer_done: bool) -> int:
        """Determine the safe position up to which we can yield chunks."""
        potential_key_pos = self._find_potential_key_position(accumulated)
        if potential_key_pos >= 0 and not producer_done:
            return potential_key_pos
        return len(accumulated)

    def _update_delay_mode(self, state: ReleaseState, y_start: int, y_end: int) -> None:
        """Update delay mode based on chunk position relative to keys."""
        # Check if should enter delay mode (after start_key)
        if not state.in_delay_mode and state.found_start_keys:
            for sk_range in state.found_start_keys:
                if y_start >= sk_range[1] or (y_start < sk_range[1] <= y_end):
                    state.in_delay_mode = True
                    break

        # Check if should exit delay mode (after end_key)
        if state.in_delay_mode and state.found_end_keys:
            for ek_range in state.found_end_keys:
                if y_start >= ek_range[1] or (y_start < ek_range[1] <= y_end):
                    state.in_delay_mode = False
                    break

    def _should_skip_to_end_key(self, state: ReleaseState, y_end: int) -> bool:
        """Check if chunk should be skipped because it's before an end_key in delay mode."""
        if not state.in_delay_mode:
            return False
        for ek_range in state.found_end_keys:
            if y_end <= ek_range[0]:
                return True
        return False

    def _get_text_to_yield(self, y_start: int, y_end: int, state: ReleaseState) -> Optional[str]:
        """
        Given a chunk's position range, return the text that should be yielded.
        Returns None if the entire chunk should be skipped.
        Handles partial overlaps with keys by extracting non-key portions.
        """
        all_key_ranges = state.found_start_keys + state.found_end_keys
        
        # Sort relevant key ranges by start position
        relevant_ranges = sorted(
            [r for r in all_key_ranges if self._chunk_overlaps_range(y_start, y_end, r[0], r[1])],
            key=lambda x: x[0]
        )
        
        if not relevant_ranges:
            return self._accumulated_text[y_start:y_end]
        
        # Extract non-key portions
        result_parts = []
        current_pos = y_start
        
        for key_start, key_end in relevant_ranges:
            text_start = max(current_pos, y_start)
            text_end = min(key_start, y_end)
            if text_end > text_start:
                result_parts.append(self._accumulated_text[text_start:text_end])
            current_pos = max(current_pos, key_end)
        
        # Add remaining text after last key
        if current_pos < y_end:
            result_parts.append(self._accumulated_text[current_pos:y_end])
        
        return "".join(result_parts) if result_parts else None

    def _try_get_next_chunk(self, state: ReleaseState) -> Tuple[Optional[Tuple[str, int, int]], str, bool]:
        """Try to get the next chunk from buffer. Returns (chunk_data, accumulated_text, producer_done)."""
        with self._lock:
            chunk_data = None
            if state.read_idx < len(self._buffer):
                chunk_data = self._buffer[state.read_idx]
            return chunk_data, self._accumulated_text, self._producer_done.is_set()

    def _get_chunk_at_yield_idx(self, state: ReleaseState) -> Optional[Tuple[str, int, int]]:
        """Get chunk data at current yield index."""
        with self._lock:
            if state.yield_idx < len(self._buffer):
                return self._buffer[state.yield_idx]
        return None

    def release(self, text_iterator: Iterator[str]) -> Iterator[str]:
        """
        Yields chunks from text_iterator with the following behavior:
        - Before start_key: yield chunks immediately (but hold back if potential key prefix)
        - After start_key (until end_key): yield with WAIT_TIME delay
        - start_key and end_key are never yielded, but text around them in same chunk is yielded
        - When end_key is seen: skip all pending chunks and resume after end_key
        - Keys can span multiple chunks, chunks are held until key is confirmed or ruled out
        """
        # Reset instance state for safe reuse
        self._buffer.clear()
        self._producer_done.clear()
        self._accumulated_text = ""

        producer_thread = threading.Thread(target=self._producer, args=(text_iterator,), daemon=True)
        producer_thread.start()

        state = ReleaseState()

        while True:
            chunk_data, accumulated, producer_done = self._try_get_next_chunk(state)

            if chunk_data is None:
                if producer_done:
                    with self._lock:
                        if state.read_idx >= len(self._buffer):
                            break
                else:
                    time.sleep(0.01)
                    continue
            
            # If it is not string; return the thing
            item, start_pos, end_pos = chunk_data
            if start_pos is None:  # Non-string item - yield immediately
                state.read_idx += 1  # <-- ADD THIS LINE
                state.yield_idx = state.read_idx  # Skip past this in yield tracking
                yield item
                continue

            state.read_idx += 1
            self._search_for_keys(state, len(accumulated))
            safe_end_pos = self._get_safe_end_pos(accumulated, producer_done)

            # Process chunks ready to yield
            while state.yield_idx < state.read_idx:
                chunk_at_yield = self._get_chunk_at_yield_idx(state)
                if chunk_at_yield is None:
                    break

                y_chunk, y_start, y_end = chunk_at_yield

                if y_end > safe_end_pos and not producer_done:
                    break

                self._update_delay_mode(state, y_start, y_end)

                if self._should_skip_to_end_key(state, y_end):
                    state.yield_idx += 1
                    continue

                state.yield_idx += 1
                text_to_yield = self._get_text_to_yield(y_start, y_end, state)

                if not text_to_yield:
                    continue

                if state.in_delay_mode:
                    # Yield character by character with delay
                    for char in text_to_yield:
                        yield char
                        time.sleep(self.WAIT_TIME)
                else:
                    # Yield entire chunk immediately
                    yield text_to_yield


class AsyncTextReleaser:
    """
    Async version of TextReleaser for use with async generators.
    
    Controls the release rate of streaming text chunks based on special key markers.
    Uses asyncio instead of threading for non-blocking operation.
    """
    KEY_START_CHAR = "["

    def __init__(self, start_key: str = None, end_key: str = None, wait_time:float = 0.15):
        """
        Initialize the AsyncTextReleaser.
        
        Args:
            start_key: Marker that triggers delayed yielding (e.g., "[CHATTY_OUT]")
            end_key: Marker that ends delayed yielding and skips pending chunks (e.g., "[TOOL_OUT]")
        """
        self.start_key = start_key
        self.end_key = end_key
        self.WAIT_TIME = wait_time  # sec/word in chinese
        self._accumulated_text = ""

    def _is_prefix_of_key(self, text: str) -> bool:
        """Check if text is a prefix of start_key or end_key."""
        if self.start_key and self.start_key.startswith(text):
            return True
        if self.end_key and self.end_key.startswith(text):
            return True
        return False

    def _find_key_range(self, key: str, after_pos: int = 0) -> Optional[Tuple[int, int]]:
        """Find the start and end position of a key in accumulated text after given position."""
        if not key:
            return None
        idx = self._accumulated_text.find(key, after_pos)
        if idx == -1:
            return None
        return (idx, idx + len(key))

    def _chunk_overlaps_range(self, chunk_start: int, chunk_end: int, range_start: int, range_end: int) -> bool:
        """Check if chunk overlaps with a given range."""
        return not (chunk_end <= range_start or chunk_start >= range_end)

    def _search_for_keys(self, state: ReleaseState, accumulated_len: int) -> None:
        """Search for complete start_key and end_key occurrences in accumulated text."""
        while True:
            key_range = self._find_key_range(self.start_key, state.start_key_search_pos)
            if key_range and key_range[1] <= accumulated_len:
                state.found_start_keys.append(key_range)
                state.start_key_search_pos = key_range[1]
            else:
                break

        while True:
            key_range = self._find_key_range(self.end_key, state.end_key_search_pos)
            if key_range and key_range[1] <= accumulated_len:
                state.found_end_keys.append(key_range)
                state.end_key_search_pos = key_range[1]
            else:
                break

    def _find_potential_key_position(self, accumulated: str) -> int:
        """Find position of potential incomplete key at end of accumulated text."""
        max_key_len = max(len(self.start_key or ""), len(self.end_key or ""))
        for search_start in range(max(0, len(accumulated) - max_key_len + 1), len(accumulated)):
            suffix = accumulated[search_start:]
            if suffix.startswith(self.KEY_START_CHAR) and self._is_prefix_of_key(suffix):
                return search_start
        return -1

    def _get_safe_end_pos(self, accumulated: str, producer_done: bool) -> int:
        """Determine the safe position up to which we can yield chunks."""
        potential_key_pos = self._find_potential_key_position(accumulated)
        if potential_key_pos >= 0 and not producer_done:
            return potential_key_pos
        return len(accumulated)

    def _update_delay_mode(self, state: ReleaseState, y_start: int, y_end: int) -> None:
        """Update delay mode based on chunk position relative to keys."""
        if not state.in_delay_mode and state.found_start_keys:
            for sk_range in state.found_start_keys:
                if y_start >= sk_range[1] or (y_start < sk_range[1] <= y_end):
                    state.in_delay_mode = True
                    break

        if state.in_delay_mode and state.found_end_keys:
            for ek_range in state.found_end_keys:
                if y_start >= ek_range[1] or (y_start < ek_range[1] <= y_end):
                    state.in_delay_mode = False
                    break

    def _should_skip_to_end_key(self, state: ReleaseState, y_end: int) -> bool:
        """Check if chunk should be skipped because it's before an end_key in delay mode."""
        if not state.in_delay_mode:
            return False
        for ek_range in state.found_end_keys:
            if y_end <= ek_range[0]:
                return True
        return False

    def _get_text_to_yield(self, y_start: int, y_end: int, state: ReleaseState) -> Optional[str]:
        """
        Given a chunk's position range, return the text that should be yielded.
        Returns None if the entire chunk should be skipped.
        """
        all_key_ranges = state.found_start_keys + state.found_end_keys
        
        relevant_ranges = sorted(
            [r for r in all_key_ranges if self._chunk_overlaps_range(y_start, y_end, r[0], r[1])],
            key=lambda x: x[0]
        )
        
        if not relevant_ranges:
            return self._accumulated_text[y_start:y_end]
        
        result_parts = []
        current_pos = y_start
        
        for key_start, key_end in relevant_ranges:
            text_start = max(current_pos, y_start)
            text_end = min(key_start, y_end)
            if text_end > text_start:
                result_parts.append(self._accumulated_text[text_start:text_end])
            current_pos = max(current_pos, key_end)
        
        if current_pos < y_end:
            result_parts.append(self._accumulated_text[current_pos:y_end])
        
        return "".join(result_parts) if result_parts else None

    async def release(self, text_iterator: AsyncIterator[Any]) -> AsyncIterator[Any]:
        """
        Async version of release that works with async generators.
        
        Yields chunks from text_iterator with the following behavior:
        - Before start_key: yield chunks immediately (but hold back if potential key prefix)
        - After start_key (until end_key): yield with WAIT_TIME delay
        - start_key and end_key are never yielded
        - When end_key is seen: skip all pending chunks and resume after end_key
        """
        # Reset instance state for safe reuse
        self._accumulated_text = ""
        
        buffer: deque = deque()  # stores (chunk, chunk_start_pos, chunk_end_pos)
        state = ReleaseState()
        producer_done = False

        async def consume_and_process():
            nonlocal producer_done
            
            async for chunk in text_iterator:
                if isinstance(chunk, str):
                    start_pos = len(self._accumulated_text)
                    self._accumulated_text += chunk
                    end_pos = len(self._accumulated_text)
                    buffer.append((chunk, start_pos, end_pos))
                else:
                    buffer.append((chunk, None, None))
                
                # Process available chunks
                self._search_for_keys(state, len(self._accumulated_text))
                safe_end_pos = self._get_safe_end_pos(self._accumulated_text, False)
                
                while state.yield_idx < len(buffer):
                    chunk_at_yield = buffer[state.yield_idx]
                    y_chunk, y_start, y_end = chunk_at_yield
                    
                    # If it is not string; return the thing
                    if y_start is None:  # Non-string item - yield immediately
                        state.yield_idx += 1
                        yield y_chunk
                        continue
                    
                    if y_end > safe_end_pos:
                        break
                    
                    self._update_delay_mode(state, y_start, y_end)
                    
                    if self._should_skip_to_end_key(state, y_end):
                        state.yield_idx += 1
                        continue
                    
                    state.yield_idx += 1
                    text_to_yield = self._get_text_to_yield(y_start, y_end, state)
                    
                    if not text_to_yield:
                        continue
                    
                    if state.in_delay_mode:
                        for char in text_to_yield:
                            yield char
                            await asyncio.sleep(self.WAIT_TIME)
                    else:
                        yield text_to_yield
            
            producer_done = True
            
            # Process remaining chunks after producer is done
            self._search_for_keys(state, len(self._accumulated_text))
            safe_end_pos = self._get_safe_end_pos(self._accumulated_text, True)
            
            while state.yield_idx < len(buffer):
                chunk_at_yield = buffer[state.yield_idx]
                y_chunk, y_start, y_end = chunk_at_yield
                
                # If it is not string; return the thing
                if y_start is None:  # Non-string item - yield immediately
                    state.yield_idx += 1
                    yield y_chunk
                    continue
                
                self._update_delay_mode(state, y_start, y_end)
                
                if self._should_skip_to_end_key(state, y_end):
                    state.yield_idx += 1
                    continue
                
                state.yield_idx += 1
                text_to_yield = self._get_text_to_yield(y_start, y_end, state)
                
                if not text_to_yield:
                    continue
                
                if state.in_delay_mode:
                    for char in text_to_yield:
                        yield char
                        await asyncio.sleep(self.WAIT_TIME)
                else:
                    yield text_to_yield

        async for chunk in consume_and_process():
            yield chunk
