/**
 * TeacherDigitalTwinPage — full teacher analytics and simulation hub.
 *
 * Route: /courses/:id/teacher-twin
 * Access: teacher role only
 */
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, BrainCircuit } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SkillDifficultyPanel } from '../components/SkillDifficultyPanel';
import { SkillPopularityPanel } from '../components/SkillPopularityPanel';
import { ClassMasteryPanel } from '../components/ClassMasteryPanel';
import { StudentGroupsPanel } from '../components/StudentGroupsPanel';
import { WhatIfPanel } from '../components/WhatIfPanel';

export default function TeacherDigitalTwinPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const courseId = Number(id);

  return (
    <div className="space-y-6">
      {/* Back */}
      <Button
        variant="ghost"
        className="pl-0 hover:bg-transparent hover:text-primary"
        onClick={() => navigate(`/courses/${courseId}`)}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Course
      </Button>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BrainCircuit className="h-6 w-6 text-primary" />
          Teacher Digital Twin
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Class-wide analytics, student groups, and what-if curriculum simulations — powered by ARCD.
        </p>
      </div>

      {/* Feature tabs */}
      <Tabs defaultValue="difficulty">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="difficulty">Skill Difficulty</TabsTrigger>
          <TabsTrigger value="popularity">Skill Popularity</TabsTrigger>
          <TabsTrigger value="mastery">Class Mastery</TabsTrigger>
          <TabsTrigger value="groups">Student Groups</TabsTrigger>
          <TabsTrigger value="whatif">What-If Simulation</TabsTrigger>
        </TabsList>

        <TabsContent value="difficulty" className="mt-4">
          <SkillDifficultyPanel courseId={courseId} />
        </TabsContent>

        <TabsContent value="popularity" className="mt-4">
          <SkillPopularityPanel courseId={courseId} />
        </TabsContent>

        <TabsContent value="mastery" className="mt-4">
          <ClassMasteryPanel courseId={courseId} />
        </TabsContent>

        <TabsContent value="groups" className="mt-4">
          <StudentGroupsPanel courseId={courseId} />
        </TabsContent>

        <TabsContent value="whatif" className="mt-4">
          <WhatIfPanel courseId={courseId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
