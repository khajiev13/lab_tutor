import {
  Message,
  MessageAvatar,
  MessageContent,
} from "@/components/ui/message";

interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return (
    <Message className="flex-row-reverse">
      <MessageAvatar src="" alt="User" fallback="U" className="bg-muted" />
      <MessageContent className="max-w-[80%] bg-accent text-accent-foreground rounded-2xl">
        {content}
      </MessageContent>
    </Message>
  );
}
