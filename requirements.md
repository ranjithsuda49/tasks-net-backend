Setup a python based project inorder to build REST API's for Tasks Nest

TaskNest is a backend service for creating , updating and deleting tasks.

- Tasks are created by Users
- A User may or may not be part of a Group
- A Task may or may not be associated to a Group 
- An example of a Group can be family 

# Models

**User**
  - userId (Primary key)
    - name 
      - firstName
      - lastName
  - phoneNum (Optional)
  - emailId (Optional)
  - userStatus (States possible : ACTIVE / IN-ACTIVE)
  - createdAt (DateTime)
  - updatedAt (DateTime)

**Group**
  - groupId (Primary Key)
  - groupName
  - groupDesc
  - groupCategory (Family , Office etc) 
  - groupStatus (States possible : ACTIVE / IN-ACTIVE)
  - groupIconUrl
  - groupCreaterId 
        (Id of user who created group ,Foriegn key from User)
  - createdAt (DateTiem)
  - updatedAt (DateTime)

**User-Group-RelationShip**
  - uuid (UUId for Primarykey)
  - groupId (Foriegn Key to Group)
  - userId (Foriegn key to userId)
  - relationShip (Relationship of user with group
                    E.g Father, Friend , Collegue etc )

**Task**
  - taskId (Primary key)
  - taskTitle
  - taskDesc (Optional)
  - taskDueDate (By When should task be completed)
  - taskState [States possible : TODO , IN-PROGRESS , COMPLETED]
  - createdAt
  - createdBy (userId who created this task)
  - updatedAt
  - updatedBy

**Task - Group-RelationShip**
  - uuid (UUID for primary key)
  - taskId  (Foriegn key to Task)
  - groupId (Foriegn key to GroupId)
  - assigneId (Id of user who is supposed to work in a group) 

# Tech Principles / Arch : 

- Primary goal is to build the API's using FastAPI of python
- Strictly follow SOLID principles
- Don't create any DB now , primary goal initially is to work with in-memory entities


# API's Req : 

- All are v1 API's to be built. REST is protocol 

## User
    - Able to create a user
    - Able to fetch a User , given userId
    - Able to update information about user 
        (name ,phoneNumber, emailId)
    - Able to mark his/her status as ACTIVE /IN-ACTIVE
  
## Group
    - Able to create a group by a user
    - Able to fetch all groups created by user , given userId
    - Able to fetch group give groupId
    - Able to upate group information , given groupId
      - (name , desc , iconUrl) 
      - Note : We don't want category to be updated once created 
    - Able to mark group status as ACTIVE / IN-ACTIVE
  
## User-Group RelationShip
    - Able to associate User to a group     (add row)
    - Able to de-associate User from group  (delete row)
  
## Tasks
    - Able to create a task
    - Able to update task meta status 
      - title , desc
    - Able to move task status from state1 -> state2
    - Able to update due date of task
  
## Task - Group RelationShip
    - Able to assign a task to assigneId(user) in a group
    - Able to remove assigne of task from assigneId (user) in a group


# Testing Plan : 

- Need to Unit test all API's 
- Need to perform Integration testing for above use cases
  

