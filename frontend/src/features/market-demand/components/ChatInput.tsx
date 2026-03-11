import { useState, useCallback } from "react";
import { ArrowUp, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputActions,
  PromptInputAction,
} from "@/components/ui/prompt-input";

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onStop, isStreaming, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setValue("");
  }, [value, isStreaming, onSend]);

  return (
    <PromptInput
      value={value}
      onValueChange={setValue}
      onSubmit={handleSubmit}
      disabled={isStreaming || disabled}
    >
      <PromptInputTextarea placeholder="Type your response..." />
      <PromptInputActions className="justify-end px-2 pb-2">
        {isStreaming ? (
          <PromptInputAction tooltip="Stop streaming">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive"
              onClick={onStop}
            >
              <Square className="size-4" />
            </Button>
          </PromptInputAction>
        ) : (
          <PromptInputAction tooltip="Send message">
            <Button
              size="icon"
              className="h-8 w-8"
              disabled={!value.trim() || disabled}
              onClick={handleSubmit}
            >
              <ArrowUp className="size-4" />
            </Button>
          </PromptInputAction>
        )}
      </PromptInputActions>
    </PromptInput>
  );
}
