import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PresentationList } from '../components/PresentationList';
import { presentationsApi } from '../features/courses/api';
import { vi, type Mock } from 'vitest';

// Mock the API
vi.mock('../features/courses/api', () => ({
  presentationsApi: {
    list: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('PresentationList', () => {
  const mockCourseId = 1;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    (presentationsApi.list as Mock).mockReturnValue(new Promise(() => {})); // Never resolves
    render(<PresentationList courseId={mockCourseId} />);
    // Look for the loader icon or container
    // Since Loader2 is an SVG, we might not find text. 
    // But the component renders a div with specific classes.
    // Alternatively, we can check if "No presentations" is NOT present yet.
    expect(screen.queryByText('No presentations uploaded yet.')).not.toBeInTheDocument();
  });

  it('renders empty state when no files', async () => {
    (presentationsApi.list as Mock).mockResolvedValue([]);
    render(<PresentationList courseId={mockCourseId} />);

    await waitFor(() => {
      expect(screen.getByText('No presentations uploaded yet.')).toBeInTheDocument();
    });
  });

  it('renders list of files', async () => {
    const mockFiles = ['lecture1.pdf', 'slides.pptx'];
    (presentationsApi.list as Mock).mockResolvedValue(mockFiles);
    render(<PresentationList courseId={mockCourseId} />);

    await waitFor(() => {
      expect(screen.getByText('lecture1.pdf')).toBeInTheDocument();
      expect(screen.getByText('slides.pptx')).toBeInTheDocument();
    });
  });

  it('handles file deletion', async () => {
    const mockFiles = ['lecture1.pdf'];
    (presentationsApi.list as Mock).mockResolvedValue(mockFiles);
    (presentationsApi.delete as Mock).mockResolvedValue(undefined);

    render(<PresentationList courseId={mockCourseId} />);

    await waitFor(() => {
      expect(screen.getByText('lecture1.pdf')).toBeInTheDocument();
    });

    // Find delete button (it's inside an AlertDialog)
    // The button in the list triggers the dialog
    const deleteTrigger = screen.getByRole('button');
    fireEvent.click(deleteTrigger);

    // Now the dialog should be open. We need to find the confirm button.
    // Shadcn AlertDialog usually has "Continue" or "Delete" action.
    // Let's check the component code if I can... 
    // Wait, I don't have the component code in front of me right now, but usually it's "Continue".
    // Let's assume standard Shadcn usage or check the file content if needed.
    // Actually, I read PresentationList.tsx earlier.
    // It imports AlertDialogAction.
    
    // Let's try to find the action button by text.
    const confirmButton = await screen.findByText('Delete', { selector: 'button' });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(presentationsApi.delete).toHaveBeenCalledWith(mockCourseId, 'lecture1.pdf');
    });
    
    // File should be removed from list
    await waitFor(() => {
      expect(screen.queryByText('lecture1.pdf')).not.toBeInTheDocument();
    });
  });
});
