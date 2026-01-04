import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, type Mock } from 'vitest';

import CourseGraphPage from '../features/graph/pages/CourseGraphPage';
import { coursesApi } from '../features/courses/api';

vi.mock('../features/courses/api', () => ({
  coursesApi: {
    getCourseGraph: vi.fn(),
    expandCourseGraph: vi.fn(),
  },
}));

vi.mock('../features/graph/components/GraphViewer', () => ({
  GraphViewer: ({
    graph,
    onExpand,
  }: {
    graph: { nodes: Array<{ id: string; label: string; kind: string; data: unknown }> };
    onExpand: (node: { id: string; label: string; kind: string; data: unknown }) => Promise<void>;
  }) => (
    <div>
      <div data-testid="graph-labels">{graph.nodes.map((n) => n.label).join(', ')}</div>
      <button type="button" onClick={() => onExpand(graph.nodes[0])}>
        Expand
      </button>
    </div>
  ),
}));

describe('CourseGraphPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderPage = () => {
    render(
      <MemoryRouter initialEntries={['/courses/1/graph']}>
        <Routes>
          <Route path="/courses/:id/graph" element={<CourseGraphPage />} />
        </Routes>
      </MemoryRouter>
    );
  };

  it('renders a graph label after loading', async () => {
    (coursesApi.getCourseGraph as Mock).mockResolvedValue({
      nodes: [{ id: 'class_1', kind: 'class', label: 'Test Course', data: { course_id: 1 } }],
      edges: [],
    });
    (coursesApi.expandCourseGraph as Mock).mockResolvedValue({ nodes: [], edges: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('graph-labels')).toHaveTextContent('Test Course');
    });
  });

  it('shows an error message when loading fails', async () => {
    (coursesApi.getCourseGraph as Mock).mockRejectedValue(new Error('boom'));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Could not load graph')).toBeInTheDocument();
    });
  });

  it('calls expand API when Expand is triggered', async () => {
    (coursesApi.getCourseGraph as Mock).mockResolvedValue({
      nodes: [{ id: 'class_1', kind: 'class', label: 'Test Course', data: { course_id: 1 } }],
      edges: [],
    });
    (coursesApi.expandCourseGraph as Mock).mockResolvedValue({
      nodes: [{ id: 'concept_x', kind: 'concept', label: 'x', data: { name: 'x' } }],
      edges: [],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('graph-labels')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Expand'));

    await waitFor(() => {
      expect(coursesApi.expandCourseGraph).toHaveBeenCalled();
    });
  });
});





