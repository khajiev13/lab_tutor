import { Calendar, Clock, BookOpen } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function SchedulePage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Calendar className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">Schedule</h1>
          <p className="text-sm text-muted-foreground">
            Your upcoming study sessions and practice reminders
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4 text-primary" />
              Today
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground text-center py-8">
              No sessions scheduled for today.
              <br />
              <span className="text-xs">
                Complete your skills in the Learning Path to get personalised study times.
              </span>
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-primary" />
              Upcoming
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {['Review session', 'Spaced repetition', 'Practice quiz'].map((item) => (
              <div key={item} className="flex items-center justify-between rounded-lg border px-3 py-2">
                <span className="text-sm">{item}</span>
                <Badge variant="outline" className="text-xs">Coming soon</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="border-dashed">
        <CardContent className="py-10 text-center space-y-2">
          <Calendar className="h-10 w-10 text-muted-foreground/40 mx-auto" />
          <p className="text-sm font-medium">Adaptive Scheduling</p>
          <p className="text-xs text-muted-foreground max-w-sm mx-auto">
            ARCD will automatically suggest spaced-repetition review sessions based on your
            mastery decay rates. Lock your skills in the Learning Path to enable this feature.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
