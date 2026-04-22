import { useState } from "react"
import {
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronsUpDown,
  FlaskConical,
  GitBranch,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  MapPin,
  Route,
  Sparkles,
  User,
  BrainCircuit,
  ListOrdered,
} from "lucide-react"
import { useAuth } from "@/features/auth/context/AuthContext"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Link, useLocation } from "react-router-dom"

export function AppSidebar() {
  const { user, logout } = useAuth()
  const location = useLocation()

  // Extract course ID from the current URL to build ARCD links
  const courseMatch = location.pathname.match(/^\/courses\/(\d+)/)
  const courseId = courseMatch?.[1] ?? null
  const isOnCoursePage = !!courseId

  const [arcdOpen, setArcdOpen] = useState(true)

  const isActive = (url: string) => location.pathname === url
  const isArcdActive = (sub: string) =>
    courseId
      ? location.pathname === `/courses/${courseId}/arcd/${sub}` ||
        (location.pathname === `/courses/${courseId}/arcd` && sub === "")
      : false

  const globalItems = [
    { title: "Dashboard", url: "/home", icon: LayoutDashboard },
    { title: "My Courses", url: "/courses", icon: BookOpen },
    { title: "Profile", url: "/profile", icon: User },
  ]

  const UserIcon = user?.role === "teacher" ? BookOpen : GraduationCap
  const arcdBase = courseId ? `/courses/${courseId}/arcd` : "#"
  const isTeacher = user?.role === "teacher"

  // ── Teacher ARCD navigation (flat 3-item list) ──────────────────────────
  const teacherArcdItems = [
    { title: "Class Overview", url: `${arcdBase}`, icon: LayoutDashboard, sub: "" },
    { title: "Class Roster & Scores", url: `${arcdBase}/roster`, icon: ListOrdered, sub: "roster" },
    { title: "Teacher Twin", url: `${arcdBase}/teacher-twin`, icon: BrainCircuit, sub: "teacher-twin" },
  ]

  // ── Student ARCD navigation ──────────────────────────────────────────────
  const studentProfileItems = [
    { title: "Overview", url: `${arcdBase}`, icon: LayoutDashboard, sub: "" },
    { title: "Student Page", url: `${arcdBase}/student`, icon: User, sub: "student" },
    { title: "Journey Map", url: `${arcdBase}/journey`, icon: MapPin, sub: "journey" },
    { title: "Schedule", url: `${arcdBase}/schedule`, icon: CalendarDays, sub: "schedule" },
  ]

  const learningItems = [
    { title: "Learning Path", url: `${arcdBase}/learning-path`, icon: Route, sub: "learning-path" },
    { title: "Quiz", url: `${arcdBase}/quiz-lab`, icon: FlaskConical, sub: "quiz-lab" },
    { title: "Review", url: `${arcdBase}/review`, icon: BookOpen, sub: "review" },
    { title: "Digital Twin", url: `${arcdBase}/digital-twin`, icon: GitBranch, sub: "digital-twin" },
  ]

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="flex items-center justify-center py-4">
        <Link
          to="/home"
          className="flex items-center gap-2 font-bold text-xl px-4 w-full group-data-[collapsible=icon]:hidden"
        >
          <span>Lab Tutor</span>
        </Link>
      </SidebarHeader>

      <SidebarContent>
        {/* ── Global Menu ──────────────────────────────── */}
        <SidebarGroup>
          <SidebarGroupLabel>Menu</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {globalItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild isActive={isActive(item.url)}>
                    <Link to={item.url}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* ── ARCD Agent (collapsible, visible when on a course) ── */}
        {isOnCoursePage && (
          <Collapsible open={arcdOpen} onOpenChange={setArcdOpen}>
            <SidebarGroup>
              <CollapsibleTrigger asChild>
                <SidebarGroupLabel className="cursor-pointer hover:bg-sidebar-accent rounded-md transition-colors">
                  <Sparkles className="size-4 mr-1.5 text-primary" />
                  ARCD Agent
                  <ChevronDown className={`ml-auto size-4 transition-transform ${arcdOpen ? "" : "-rotate-90"}`} />
                </SidebarGroupLabel>
              </CollapsibleTrigger>

              <CollapsibleContent>
                {isTeacher ? (
                  /* Teacher — flat 3-item navigation */
                  <SidebarGroupContent>
                    <SidebarMenu>
                      {teacherArcdItems.map((item) => (
                        <SidebarMenuItem key={item.title}>
                          <SidebarMenuButton
                            asChild
                            isActive={isArcdActive(item.sub)}
                          >
                            <Link to={item.url}>
                              <item.icon />
                              <span>{item.title}</span>
                            </Link>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      ))}
                    </SidebarMenu>
                  </SidebarGroupContent>
                ) : (
                  /* Student — grouped navigation */
                  <>
                    <SidebarGroupLabel className="text-[10px] uppercase tracking-wider mt-2">
                      Student Profile
                    </SidebarGroupLabel>
                    <SidebarGroupContent>
                      <SidebarMenu>
                        {studentProfileItems.map((item) => (
                          <SidebarMenuItem key={item.title}>
                            <SidebarMenuButton
                              asChild
                              isActive={isArcdActive(item.sub)}
                            >
                              <Link to={item.url}>
                                <item.icon />
                                <span>{item.title}</span>
                              </Link>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                        ))}
                      </SidebarMenu>
                    </SidebarGroupContent>

                    <SidebarGroupLabel className="text-[10px] uppercase tracking-wider mt-2">
                      Learning
                    </SidebarGroupLabel>
                    <SidebarGroupContent>
                      <SidebarMenu>
                        {learningItems.map((item) => (
                          <SidebarMenuItem key={item.title}>
                            <SidebarMenuButton
                              asChild
                              isActive={isArcdActive(item.sub)}
                            >
                              <Link to={item.url}>
                                <item.icon />
                                <span>{item.title}</span>
                              </Link>
                            </SidebarMenuButton>
                          </SidebarMenuItem>
                        ))}
                      </SidebarMenu>
                    </SidebarGroupContent>
                  </>
                )}
              </CollapsibleContent>
            </SidebarGroup>
          </Collapsible>
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                    <UserIcon className="size-4" />
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">
                      {user?.first_name} {user?.last_name}
                    </span>
                    <span className="truncate text-xs">{user?.email}</span>
                  </div>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                side="bottom"
                align="end"
                sideOffset={4}
              >
                <DropdownMenuItem onClick={logout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
