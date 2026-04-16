import unittest

from planner import Planner


class PlannerTests(unittest.TestCase):
    def test_generates_system_status_plan(self):
        tasks = Planner().create_plan("report system status")
        self.assertEqual(3, len(tasks))
        self.assertEqual("get_system_info", tasks[0].tool_name)
        self.assertEqual("list_projects", tasks[1].tool_name)
        self.assertEqual("list_saved_notes", tasks[2].tool_name)

    def test_generates_download_preview_for_organize_goal(self):
        tasks = Planner().create_plan("organize downloads")
        self.assertEqual(1, len(tasks))
        self.assertEqual("preview_folder_organization", tasks[0].tool_name)

    def test_generates_list_path_plan_for_downloads_listing(self):
        tasks = Planner().create_plan("list files in downloads")
        self.assertEqual(1, len(tasks))
        self.assertEqual("list_path", tasks[0].tool_name)
        self.assertEqual("downloads", tasks[0].tool_input["path_name"])

    def test_generates_open_folder_plan_for_downloads_folder(self):
        tasks = Planner().create_plan("open downloads folder")
        self.assertEqual(1, len(tasks))
        self.assertEqual("open_folder", tasks[0].tool_name)
        self.assertEqual("downloads", tasks[0].tool_input["path_name"])

    def test_generates_home_workspace_preview_for_workspace_status(self):
        tasks = Planner().create_plan("home workspace status")
        self.assertEqual(1, len(tasks))
        self.assertEqual("preview_home_workspace_organization", tasks[0].tool_name)

    def test_generates_workspace_summary_plan(self):
        tasks = Planner().create_plan("workspace summary")
        self.assertEqual(1, len(tasks))
        self.assertEqual("build_workspace_summary", tasks[0].tool_name)

    def test_generates_project_inspection_plan(self):
        tasks = Planner().create_plan("inspect project RogueAI")
        self.assertEqual(1, len(tasks))
        self.assertEqual("inspect_project", tasks[0].tool_name)
        self.assertEqual("RogueAI", tasks[0].tool_input["project_name"])

    def test_generates_folder_summary_plan(self):
        tasks = Planner().create_plan("summarize folder downloads")
        self.assertEqual(1, len(tasks))
        self.assertEqual("summarize_folder", tasks[0].tool_name)
        self.assertEqual("downloads", tasks[0].tool_input["path_name"])

    def test_generates_folder_summary_plan_for_natural_scan_phrase(self):
        tasks = Planner().create_plan("scan desktop")
        self.assertEqual(1, len(tasks))
        self.assertEqual("summarize_folder", tasks[0].tool_name)
        self.assertEqual("desktop", tasks[0].tool_input["path_name"])

    def test_generates_folder_summary_plan_for_natural_inspection_phrase(self):
        tasks = Planner().create_plan("inspect downloads")
        self.assertEqual(1, len(tasks))
        self.assertEqual("summarize_folder", tasks[0].tool_name)
        self.assertEqual("downloads", tasks[0].tool_input["path_name"])

    def test_generates_preview_organization_plan_for_desktop(self):
        tasks = Planner().create_plan("organize my desktop")
        self.assertEqual(1, len(tasks))
        self.assertEqual("preview_folder_organization", tasks[0].tool_name)
        self.assertEqual("desktop", tasks[0].tool_input["path_name"])
        self.assertFalse(tasks[0].tool_input["recursive"])

    def test_generates_preview_organization_plan_for_documents(self):
        tasks = Planner().create_plan("organize documents")
        self.assertEqual(1, len(tasks))
        self.assertEqual("preview_folder_organization", tasks[0].tool_name)
        self.assertEqual("documents", tasks[0].tool_input["path_name"])

    def test_generates_preview_organization_plan_for_this_folder(self):
        tasks = Planner().create_plan("organize this folder")
        self.assertEqual(1, len(tasks))
        self.assertEqual("preview_folder_organization", tasks[0].tool_name)
        self.assertEqual("workspace", tasks[0].tool_input["path_name"])
        self.assertFalse(tasks[0].tool_input["recursive"])

    def test_generates_recursive_preview_plan_for_cleanup_phrase(self):
        tasks = Planner().create_plan("clean up my desktop")
        self.assertEqual(1, len(tasks))
        self.assertEqual("preview_folder_organization", tasks[0].tool_name)
        self.assertEqual("desktop", tasks[0].tool_input["path_name"])
        self.assertTrue(tasks[0].tool_input["recursive"])


if __name__ == "__main__":
    unittest.main()
