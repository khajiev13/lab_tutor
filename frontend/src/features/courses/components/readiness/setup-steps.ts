import { BookOpen, GitBranch, Send, TrendingUp } from "lucide-react";

export const SETUP_STEPS = {
  book: {
    title: "Prepare course",
    description: "Upload your teaching materials, choose relevant books, and build your course's book skill bank.",
    action: "Continue to prepare course",
    icon: BookOpen,
  },
  market: {
    title: "Add market skills",
    description: "Explore relevant job postings and choose the industry skills you want to include in this course.",
    action: "Continue to market skills",
    icon: TrendingUp,
  },
  prerequisites: {
    title: "Review prerequisites",
    description: "Check which skills students need to learn first, then approve their learning order.",
    action: "Continue to review prerequisites",
    icon: GitBranch,
  },
  publish: {
    title: "Publish course",
    description: "Your course is ready. Publish it to let students enroll and build their learning paths.",
    action: "Publish course",
    icon: Send,
  },
};
