"""
Memory bridge between Omni Vox conversations and OpenClaw agent memory system.
Syncs significant voice conversations to agent's daily memory files.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List
import logging
from conversation import Turn, ConversationBuffer

logger = logging.getLogger(__name__)


class MemoryBridge:
    """Bridges voice conversations with OpenClaw agent memory system.
    
    Syncs conversation summaries to daily memory files for cross-channel
    memory consistency and long-term memory integration.
    """
    
    def __init__(self, sessions_dir: str = "/sessions", memory_sync_interval: int = 5):
        self.sessions_dir = Path(sessions_dir)
        self.memory_sync_interval = memory_sync_interval  # turns between syncs
        self.last_sync_counts = {}  # track when we last synced each session
    
    def should_sync_session(self, session_key: str, turn_count: int) -> bool:
        """Determine if we should sync this session to memory files"""
        last_sync = self.last_sync_counts.get(session_key, 0)
        
        # Sync every N turns, or if it's been more than 10 turns since last sync
        return (
            turn_count - last_sync >= self.memory_sync_interval or
            turn_count - last_sync >= 10
        )
    
    def format_conversation_summary(self, session_key: str, turns: List[Turn], 
                                   is_partial: bool = True) -> str:
        """Format conversation turns into a memory-friendly summary"""
        if not turns:
            return ""
        
        # Get the time range for this batch of turns
        start_time = datetime.fromtimestamp(turns[0].timestamp)
        end_time = datetime.fromtimestamp(turns[-1].timestamp)
        
        # Format timestamp
        time_str = start_time.strftime("%-I:%M %p")
        if start_time.date() != end_time.date() or (end_time.timestamp() - start_time.timestamp()) > 3600:
            # Include end time if conversation spans significant time
            time_str += f" - {end_time.strftime('%-I:%M %p')}"
        
        # Build conversation summary
        lines = [f"### Voice Conversation - {time_str}"]
        
        if is_partial:
            lines.append(f"*[{len(turns)} turns from ongoing conversation]*")
        else:
            lines.append(f"*[Complete conversation - {len(turns)} turns]*")
        
        lines.append("")
        
        # Include recent turns (limit to avoid huge memory entries)
        display_turns = turns[-8:] if len(turns) > 8 else turns
        if len(turns) > 8:
            lines.append(f"*[Showing last 8 of {len(turns)} turns]*")
            lines.append("")
        
        for turn in display_turns:
            lines.append(f"> **Chris:** \"{turn.user}\"")
            lines.append(f"**Omni:** {turn.assistant}")
            lines.append("")
        
        # Add conversation metadata
        lines.append(f"*Duration: ~{int((end_time.timestamp() - start_time.timestamp()) / 60)} minutes*")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        return "\n".join(lines)
    
    def get_daily_memory_path(self, date_override: Optional[datetime] = None) -> Path:
        """Get path to today's daily memory file"""
        target_date = date_override or datetime.now()
        date_str = target_date.strftime("%Y-%m-%d")
        return Path("/root/.openclaw/workspace/memory") / f"{date_str}.md"
    
    def append_to_daily_memory(self, content: str, date_override: Optional[datetime] = None) -> bool:
        """Append content to the daily memory file"""
        memory_path = self.get_daily_memory_path(date_override)
        
        try:
            # Ensure memory directory exists
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file exists, create with header if not
            if not memory_path.exists():
                date_str = (date_override or datetime.now()).strftime("%B %d, %Y")
                header = f"# Daily Memory — {date_str}\n\n"
                with open(memory_path, 'w', encoding='utf-8') as f:
                    f.write(header)
            
            # Append the content
            with open(memory_path, 'a', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Appended conversation summary to {memory_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write to daily memory {memory_path}: {e}")
            return False
    
    def sync_conversation_to_memory(self, session_key: str, conversation_buffer: ConversationBuffer) -> bool:
        """Sync a conversation session to daily memory files"""
        turns = conversation_buffer.get_history(session_key)
        if not turns:
            return False
        
        current_turn_count = len(turns)
        last_synced_count = self.last_sync_counts.get(session_key, 0)
        
        # Get only the new turns since last sync
        new_turns = turns[last_synced_count:] if last_synced_count > 0 else turns
        if not new_turns:
            return False
        
        # Format and append to daily memory
        summary = self.format_conversation_summary(
            session_key, 
            new_turns, 
            is_partial=True
        )
        
        # Determine which day to write to (use the timestamp of the first new turn)
        target_date = datetime.fromtimestamp(new_turns[0].timestamp)
        success = self.append_to_daily_memory(summary, target_date)
        
        if success:
            # Update our sync tracking
            self.last_sync_counts[session_key] = current_turn_count
            logger.info(f"Synced {len(new_turns)} new turns from session '{session_key}' to memory")
        
        return success
    
    def sync_session_if_needed(self, session_key: str, conversation_buffer: ConversationBuffer) -> bool:
        """Check if session needs syncing and sync if so"""
        turn_count = conversation_buffer.turn_count(session_key)
        
        if self.should_sync_session(session_key, turn_count):
            return self.sync_conversation_to_memory(session_key, conversation_buffer)
        
        return False
    
    def finalize_conversation(self, session_key: str, conversation_buffer: ConversationBuffer) -> bool:
        """Mark a conversation as complete and do final sync"""
        turns = conversation_buffer.get_history(session_key)
        if not turns:
            return False
        
        # Do a final sync of any remaining turns
        success = self.sync_conversation_to_memory(session_key, conversation_buffer)
        
        # Optionally write a completion marker
        if success:
            completion_note = f"\n*[Voice conversation '{session_key}' ended - {len(turns)} total turns]*\n\n"
            target_date = datetime.fromtimestamp(turns[-1].timestamp)
            self.append_to_daily_memory(completion_note, target_date)
        
        # Reset sync counter for this session
        self.last_sync_counts.pop(session_key, None)
        
        return success
    
    def get_recent_voice_context(self, session_key: str = "voice", hours_back: int = 24) -> Optional[str]:
        """Get recent voice conversation context for cross-channel consistency.
        
        This can be used by the main OpenClaw agent to understand recent voice
        interactions when responding in Discord or other channels.
        """
        cutoff_time = time.time() - (hours_back * 3600)
        
        # Look through recent daily memory files for voice conversation entries
        context_entries = []
        
        for days_back in range(3):  # Check last 3 days
            check_date = datetime.now() - timedelta(days=days_back)
            memory_path = self.get_daily_memory_path(check_date)
            
            if memory_path.exists():
                try:
                    with open(memory_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Extract voice conversation sections
                    lines = content.split('\n')
                    in_voice_section = False
                    current_section = []
                    
                    for line in lines:
                        if '### Voice Conversation' in line:
                            if current_section:
                                # Save previous section
                                context_entries.append('\n'.join(current_section))
                            current_section = [line]
                            in_voice_section = True
                        elif in_voice_section:
                            current_section.append(line)
                            if line.strip() == '---' and len(current_section) > 5:
                                # End of voice section
                                context_entries.append('\n'.join(current_section))
                                current_section = []
                                in_voice_section = False
                    
                    # Handle final section
                    if current_section:
                        context_entries.append('\n'.join(current_section))
                        
                except Exception as e:
                    logger.error(f"Failed to read memory file {memory_path}: {e}")
        
        if context_entries:
            # Return the most recent few voice conversations as context
            recent_entries = context_entries[-3:] if len(context_entries) > 3 else context_entries
            return f"[Recent voice interactions for context:]\n" + "\n\n".join(recent_entries)
        
        return None