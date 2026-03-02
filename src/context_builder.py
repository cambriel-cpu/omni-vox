"""
ContextBuilder for voice conversation memory system.
Assembles complete conversation context for LLM requests - critical path component.
"""
import time
from dataclasses import dataclass
from typing import List
from .layered_memory import LayeredMemorySystem
from .session_manager import ConversationTurn


@dataclass
class ContextRequest:
    """Request for context building with configuration options"""
    session_id: str
    current_input: str
    max_context_length: int = 4000
    include_personality: bool = True
    include_memory_search: bool = False


@dataclass
class ContextResponse:
    """Response containing formatted context and performance metrics"""
    formatted_context: str
    context_summary: str
    tokens_used: int
    performance_ms: float


class ContextBuilder:
    """Builds conversation context for LLM requests with performance optimization"""
    
    def __init__(self, memory_system: LayeredMemorySystem,
                 personality_prompt: str = "You are Omni, a helpful AI assistant."):
        """Initialize context builder with memory system and personality"""
        self.memory_system = memory_system
        self.personality_prompt = personality_prompt
    
    def build_context(self, request: ContextRequest) -> ContextResponse:
        """Build complete context for LLM request (<5ms target)"""
        start_time = time.time()
        
        # Get conversation history from memory
        conversation_turns = self.memory_system.get_immediate_context(
            request.session_id, turns=10
        )
        
        # Build context components
        context_parts = []
        
        # Add personality prompt if requested
        if request.include_personality:
            context_parts.append(f"System: {self.personality_prompt}")
        
        # Add conversation history  
        if conversation_turns:
            context_parts.append("Conversation History:")
            for turn in conversation_turns:
                context_parts.append(f"User: {turn.user_input}")
                context_parts.append(f"Assistant: {turn.assistant_response}")
        
        # Add current input
        context_parts.append(f"User: {request.current_input}")
        
        # Join and measure context
        full_context = "\n".join(context_parts)
        
        # Truncate if needed (rough token estimation)
        if len(full_context) > request.max_context_length * 4:  # ~4 chars per token
            full_context = self._truncate_context(full_context, request.max_context_length)
        
        # Calculate performance metrics
        end_time = time.time()
        performance_ms = (end_time - start_time) * 1000
        
        # Token estimation
        estimated_tokens = len(full_context) // 4
        
        # Generate summary
        summary = f"Context with {len(conversation_turns)} turns, {estimated_tokens} tokens"
        
        return ContextResponse(
            formatted_context=full_context,
            context_summary=summary,
            tokens_used=estimated_tokens,
            performance_ms=performance_ms
        )
    
    def format_for_llm(self, turns: List[ConversationTurn], 
                       current_input: str, personality: str) -> str:
        """Format conversation turns for LLM consumption"""
        parts = []
        
        if personality:
            parts.append(f"System: {personality}")
        
        if turns:
            parts.append("Conversation History:")
            for turn in turns:
                parts.append(f"User: {turn.user_input}")
                parts.append(f"Assistant: {turn.assistant_response}")
        
        parts.append(f"User: {current_input}")
        
        return "\n".join(parts)
    
    def _truncate_context(self, context: str, max_tokens: int) -> str:
        """Smart context truncation to fit token limits"""
        lines = context.split("\n")
        max_chars = max_tokens * 4  # Token-to-character conversion
        
        if len(context) <= max_chars:
            return context
        
        # Keep system prompt and current input, trim middle
        keep_lines = []
        current_input_line = None
        system_line = None
        
        for i, line in enumerate(lines):
            if line.startswith("System:"):
                system_line = line
            elif line.startswith("User:") and i == len(lines) - 1:
                current_input_line = line
        
        # Add essential lines
        if system_line:
            keep_lines.append(system_line)
        
        # Add as much recent conversation as possible
        conversation_lines = [line for line in lines 
                            if not line.startswith("System:") 
                            and line != current_input_line
                            and line.strip() != "Conversation History:"]
        
        # Work backwards to fit in limit
        current_length = len("\n".join(keep_lines))
        if current_input_line:
            current_length += len(current_input_line) + 1
        
        for line in reversed(conversation_lines):
            if current_length + len(line) + 1 < max_chars:
                keep_lines.append(line)
                current_length += len(line) + 1
            else:
                break
        
        # Reconstruct with proper order
        final_lines = []
        if system_line:
            final_lines.append(system_line)
        
        recent_conversation = [line for line in keep_lines if not line.startswith("System:")]
        if recent_conversation:
            final_lines.append("Conversation History:")
            recent_conversation.reverse()  # Back to chronological order
            final_lines.extend(recent_conversation)
        
        if current_input_line:
            final_lines.append(current_input_line)
        
        return "\n".join(final_lines)
