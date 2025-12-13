# Frontend Implementation Prompts

Use these prompts to guide the frontend development for the Course Presentation features.

## Prompt 1: API Integration & Types

**Context:**
The backend has new endpoints for managing course presentations:
- `POST /courses/{id}/presentations`: Upload multiple files (multipart/form-data).
- `GET /courses/{id}/presentations`: List filenames (returns `string[]`).
- `DELETE /courses/{id}/presentations/{filename}`: Delete a specific file.
- `DELETE /courses/{id}/presentations`: Delete all files.

**Task:**
1.  Update `src/types/index.ts` (or where types are defined) to include any necessary types for file handling if needed (though the API returns simple strings or success messages).
2.  Update `src/services/api.ts` to add a `presentationsApi` object with the following methods:
    - `upload(courseId: number, files: File[]): Promise<void>`
    - `list(courseId: number): Promise<string[]>`
    - `delete(courseId: number, filename: string): Promise<void>`
    - `deleteAll(courseId: number): Promise<void>`

**Note:** Ensure `upload` uses `FormData` and sets `Content-Type: multipart/form-data`.

---

## Prompt 2: Modern File Upload Component

**Context:**
We need a modern, drag-and-drop capable file upload component. We are using React 19, TailwindCSS v4, and Shadcn UI.

**Task:**
1.  Install `react-dropzone` for handling drag-and-drop interactions: `npm install react-dropzone`.
2.  Create a reusable component `src/components/FileUpload.tsx`.
3.  **Features:**
    - Drag and drop zone with visual feedback (active/inactive states).
    - "Click to select" fallback.
    - Display list of selected files *before* upload with an option to remove them from the selection.
    - A "Upload" button that triggers the API call.
    - Progress indication (optional but recommended) or loading state during upload.
    - Use `lucide-react` icons (e.g., `UploadCloud`, `File`, `X`).
    - Style it using TailwindCSS to match the Shadcn UI aesthetic (clean borders, muted text for instructions).

---

## Prompt 3: Presentation List & Management UI

**Context:**
Teachers need to see the files they've uploaded and manage them.

**Task:**
1.  Create a component `src/components/PresentationList.tsx`.
2.  **Features:**
    - Fetch and display the list of files using `presentationsApi.list`.
    - Display files in a clean list or grid.
    - Each file should have a "Delete" button (use a trash icon from `lucide-react`).
    - Add a "Delete All" button at the top (maybe inside an Alert Dialog for safety).
    - Use `sonner` for toast notifications on success/error.
3.  **Integration:**
    - Combine `FileUpload` and `PresentationList` into the Course Details or Edit page.
    - When a file is successfully uploaded via `FileUpload`, automatically refresh the `PresentationList`.

---

## Prompt 4: Full Page Integration (Example)

**Task:**
Integrate the above components into the `CourseDetails` page (only visible to Teachers).

**Requirements:**
- Check `user.role === 'teacher'` before showing the upload/delete controls.
- Students should only see the list of files (read-only view) - *Note: Backend currently allows students to list files if authenticated.*
- Ensure the UI is responsive.
