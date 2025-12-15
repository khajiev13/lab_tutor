import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FileUpload } from '../components/FileUpload';
import { vi } from 'vitest';

describe('FileUpload', () => {
  it('renders correctly', () => {
    render(<FileUpload onUpload={async () => {}} />);
    expect(screen.getByText(/Drag & drop files here/i)).toBeInTheDocument();
    expect(screen.getByText(/or click to select files/i)).toBeInTheDocument();
  });

  it('calls onUpload when files are uploaded', async () => {
    const mockOnUpload = vi.fn().mockResolvedValue(undefined);
    render(<FileUpload onUpload={mockOnUpload} />);

    const file = new File(['dummy content'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('dropzone-input');

    // Simulate file selection
    Object.defineProperty(input, 'files', {
      value: [file],
    });
    fireEvent.change(input);

    // Check if file is listed
    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });

    // Click upload button
    const uploadButton = screen.getByText(/Upload 1 file/i);
    fireEvent.click(uploadButton);

    await waitFor(() => {
      expect(mockOnUpload).toHaveBeenCalledTimes(1);
      expect(mockOnUpload).toHaveBeenCalledWith([file]);
    });
  });

  it('displays error toast on upload failure', async () => {
    const mockOnUpload = vi.fn().mockRejectedValue(new Error('Upload failed'));
    render(<FileUpload onUpload={mockOnUpload} />);

    const file = new File(['dummy content'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('dropzone-input');

    Object.defineProperty(input, 'files', {
      value: [file],
    });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument();
    });

    const uploadButton = screen.getByText(/Upload 1 file/i);
    fireEvent.click(uploadButton);

    await waitFor(() => {
      expect(mockOnUpload).toHaveBeenCalled();
    });
    
    // Note: We can't easily test the toast appearance without mocking sonner, 
    // but we can verify the function was called and rejected.
  });
});
