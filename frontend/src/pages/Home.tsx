import { useAuth } from '@/context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import {
  LogOut,
  GraduationCap,
  BookOpen,
  User,
  BookMarked,
  PenTool,
  Users,
  ClipboardList,
} from 'lucide-react';

export default function Home() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isTeacher = user?.role === 'teacher';
  const isStudent = user?.role === 'student';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Header */}
      <header className="border-b bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <BookMarked className="h-6 w-6 text-primary" />
            <span className="font-bold text-xl">Lab Tutor</span>
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 text-sm text-muted-foreground">
              <User className="h-4 w-4" />
              <span>{user?.email}</span>
              <span className="px-2 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium capitalize">
                {user?.role}
              </span>
            </div>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              Sign out
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {/* Welcome Section */}
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-2">
            {isTeacher ? (
              <div className="p-2 rounded-full bg-amber-100 dark:bg-amber-900/30">
                <BookOpen className="h-6 w-6 text-amber-600 dark:text-amber-400" />
              </div>
            ) : (
              <div className="p-2 rounded-full bg-blue-100 dark:bg-blue-900/30">
                <GraduationCap className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
            )}
            <div>
              <h1 className="text-3xl font-bold">
                Welcome back, {user?.first_name || user?.email?.split('@')[0]}!
              </h1>
              <p className="text-muted-foreground">
                {isTeacher
                  ? 'Ready to inspire and educate your students today?'
                  : 'Ready to learn something new today?'}
              </p>
            </div>
          </div>
        </div>

        <Separator className="my-6" />

        {/* Role-specific Dashboard */}
        {isStudent && (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <Card className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
                    <BookMarked className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <CardTitle className="text-lg">My Courses</CardTitle>
                </div>
                <CardDescription>
                  Access your enrolled courses and learning materials
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  View lectures, assignments, and resources for your courses.
                </p>
              </CardContent>
            </Card>

            <Card className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30">
                    <PenTool className="h-5 w-5 text-green-600 dark:text-green-400" />
                  </div>
                  <CardTitle className="text-lg">Lab Assignments</CardTitle>
                </div>
                <CardDescription>
                  Complete interactive lab exercises and practice
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Work on hands-on labs with AI-powered assistance.
                </p>
              </CardContent>
            </Card>

            <Card className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900/30">
                    <ClipboardList className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                  </div>
                  <CardTitle className="text-lg">My Progress</CardTitle>
                </div>
                <CardDescription>
                  Track your learning journey and achievements
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  View completed assignments, grades, and learning stats.
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        {isTeacher && (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <Card className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                    <BookOpen className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <CardTitle className="text-lg">Manage Courses</CardTitle>
                </div>
                <CardDescription>
                  Create and manage your course content
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Design lectures, add materials, and organize your curriculum.
                </p>
              </CardContent>
            </Card>

            <Card className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30">
                    <PenTool className="h-5 w-5 text-green-600 dark:text-green-400" />
                  </div>
                  <CardTitle className="text-lg">Create Labs</CardTitle>
                </div>
                <CardDescription>
                  Design interactive lab exercises for students
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Build engaging hands-on labs with AI-powered evaluation.
                </p>
              </CardContent>
            </Card>

            <Card className="hover:shadow-lg transition-shadow cursor-pointer">
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
                    <Users className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <CardTitle className="text-lg">Student Analytics</CardTitle>
                </div>
                <CardDescription>
                  Monitor student progress and performance
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  View detailed analytics on student engagement and grades.
                </p>
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
