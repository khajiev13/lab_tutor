import { ArrowUp, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PromptInput, PromptInputTextarea, PromptInputActions, PromptInputAction } from "@/components/ui/prompt-input";
import { isWorkspaceMessageValid } from "@/features/market-demand/workspace-context";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (message: string) => void;
  onCloseLiveResponse: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  sendDisabled?: boolean;
}

export function ChatInput({value, onChange, onSend, onCloseLiveResponse, isStreaming, disabled, sendDisabled}: ChatInputProps) {
  const valid = !!value.trim() && isWorkspaceMessageValid(value);
  const handleSubmit = () => {
    if (valid && !isStreaming && !disabled && !sendDisabled) onSend(value.trim());
  };
  return <PromptInput value={value} onValueChange={onChange} onSubmit={handleSubmit}>
    <PromptInputTextarea disabled={disabled} aria-label="Question" placeholder="Type your response..."/>
    {!isWorkspaceMessageValid(value) && <p role="alert" className="px-2 text-xs text-destructive">Questions can contain at most 8,000 characters.</p>}
    <PromptInputActions className="justify-end px-2 pb-2">
      {isStreaming && <PromptInputAction tooltip="Close live response">
        <Button type="button" variant="ghost" size="sm" onClick={onCloseLiveResponse} aria-label="Close live response"><Square className="size-4"/>Close live response</Button>
      </PromptInputAction>}
      <PromptInputAction tooltip="Send message">
        <Button type="button" size="icon" className="h-8 w-8" aria-label="Send message" disabled={!valid || isStreaming || disabled || sendDisabled} onClick={handleSubmit}><ArrowUp className="size-4"/></Button>
      </PromptInputAction>
    </PromptInputActions>
  </PromptInput>;
}
