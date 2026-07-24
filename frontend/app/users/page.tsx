import { UserManagement } from "@/components/users/user-management";

export default function UsersPage() {
  return <div className="page"><header className="page-header"><h1>用户管理</h1><span className="meta">管理员创建与单角色管理</span></header><div className="content-scroll"><UserManagement /></div></div>;
}
